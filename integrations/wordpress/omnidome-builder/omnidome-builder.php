<?php
/**
 * Plugin Name: OmniDome Website Builder
 * Description: Scoped draft export and reviewed publication through WordPress MCP Adapter.
 * Version: 1.0.0
 * Requires at least: 6.9
 * Requires PHP: 7.4
 * Requires Plugins: mcp-adapter
 * License: GPL-2.0-or-later
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

add_action( 'wp_abilities_api_categories_init', function () {
    wp_register_ability_category( 'omnidome', array(
        'label' => 'OmniDome', 'description' => 'Website Builder draft and publication operations.',
    ) );
} );

add_action( 'wp_abilities_api_init', function () {
    $external = array( 'type' => 'string', 'pattern' => '^[a-f0-9-]{36}$' );
    $hash = array( 'type' => 'string', 'pattern' => '^[a-f0-9]{64}$' );
    $definitions = array(
        'site-info' => array( 'properties' => array(), 'required' => array() ),
        'get-publication-status' => array( 'properties' => array( 'external_id' => $external ), 'required' => array( 'external_id' ) ),
        'publish-page' => array( 'properties' => array( 'external_id' => $external, 'exported_hash' => $hash ), 'required' => array( 'external_id', 'exported_hash' ) ),
        'upsert-page-draft' => array(
            'properties' => array(
                'external_id' => $external, 'exported_hash' => $hash,
                'title' => array( 'type' => 'string', 'minLength' => 1, 'maxLength' => 300 ),
                'slug' => array( 'type' => 'string', 'pattern' => '^[a-z0-9-]{1,100}$' ),
                'excerpt' => array( 'type' => 'string', 'maxLength' => 2000 ),
                'content' => array( 'type' => 'string', 'maxLength' => 500000 ),
                'export_version' => array( 'type' => 'integer', 'enum' => array( 1 ) ),
                'warnings' => array( 'type' => 'array', 'items' => array( 'type' => 'string' ), 'maxItems' => 10 ),
            ),
            'required' => array( 'external_id', 'exported_hash', 'title', 'slug', 'content', 'export_version', 'excerpt' ),
        ),
    );
    foreach ( $definitions as $name => $schema ) {
        $input_schema = array( 'type' => 'object', 'additionalProperties' => false );
        if ( ! empty( $schema['properties'] ) ) {
            $input_schema['properties'] = $schema['properties'];
            $input_schema['required'] = $schema['required'];
        }
        wp_register_ability( 'omnidome/' . $name, array(
            'label' => ucwords( str_replace( '-', ' ', $name ) ),
            'description' => 'OmniDome ' . $name . '. Only pages managed by this integration user are accessible.',
            'category' => 'omnidome',
            'input_schema' => $input_schema,
            'output_schema' => array( 'type' => 'object' ),
            'permission_callback' => function ( $args ) use ( $name ) {
                return current_user_can( 'edit_pages' ) &&
                    ( 'publish-page' !== $name || current_user_can( 'publish_pages' ) );
            },
            'execute_callback' => function ( $args ) use ( $name ) {
                if ( 'site-info' === $name ) {
                    return array( 'site_name' => get_bloginfo( 'name' ), 'integration_version' => 1 );
                }
                return omnidome_builder_operation( $name, $args );
            },
            'meta' => array( 'mcp' => array( 'public' => true, 'type' => 'tool' ),
                'annotations' => array( 'readonly' => 'site-info' === $name, 'idempotent' => true, 'destructive' => 'publish-page' === $name ) ),
        ) );
    }
} );

function omnidome_builder_error( $code, $message ) {
    return new WP_Error( 'omnidome_' . $code, $message );
}

function omnidome_builder_fingerprint( $post ) {
    if ( ! $post ) {
        return '';
    }
    return hash( 'sha256', wp_json_encode( array( $post->post_title, $post->post_content,
        $post->post_excerpt, $post->post_name, $post->post_status ) ) );
}

function omnidome_builder_same_content( $one, $two ) {
    return $one && $two && $one->post_title === $two->post_title &&
        $one->post_content === $two->post_content && $one->post_excerpt === $two->post_excerpt;
}

function omnidome_builder_content_hash( $post ) {
    return hash( 'sha256', wp_json_encode( array( $post->post_title, $post->post_content, $post->post_excerpt ) ) );
}

function omnidome_builder_owned_post( $id, $key ) {
    $post = get_post( $id );
    if ( ! $post || 'page' !== $post->post_type ||
         get_post_meta( $id, '_omnidome_owner', true ) !== $key || ! current_user_can( 'edit_post', $id ) ) {
        return null;
    }
    return $post;
}

function omnidome_builder_find_post( $key, $kind ) {
    $posts = get_posts( array( 'post_type' => 'page', 'post_status' => array( 'draft', 'publish', 'private', 'pending' ),
        'numberposts' => 2, 'meta_query' => array(
            array( 'key' => '_omnidome_owner', 'value' => $key ),
            array( 'key' => '_omnidome_kind', 'value' => $kind ),
        ) ) );
    if ( count( $posts ) > 1 ) {
        return omnidome_builder_error( 'duplicate', 'Multiple managed pages found; resolve them in WordPress.' );
    }
    return $posts ? omnidome_builder_owned_post( $posts[0]->ID, $key ) : null;
}

function omnidome_builder_status( &$state, $key ) {
    $draft = ! empty( $state['draft_id'] ) ? omnidome_builder_owned_post( $state['draft_id'], $key ) : null;
    if ( empty( $state['draft_id'] ) ) {
        $draft = omnidome_builder_find_post( $key, 'draft' );
        if ( is_wp_error( $draft ) ) {
            return $draft;
        }
    }
    // Recover an export whose post write succeeded but publication-record save failed.
    if ( $draft && 'draft' === $draft->post_status &&
         get_post_meta( $draft->ID, '_omnidome_exported_hash', true ) !== ( $state['exported_hash'] ?? '' ) &&
         omnidome_builder_content_hash( $draft ) === get_post_meta( $draft->ID, '_omnidome_content_hash', true ) ) {
        $state['draft_id'] = $draft->ID;
        $state['exported_hash'] = get_post_meta( $draft->ID, '_omnidome_exported_hash', true );
        $state['desired_slug'] = get_post_meta( $draft->ID, '_omnidome_desired_slug', true );
        $state['draft_fingerprint'] = omnidome_builder_fingerprint( $draft );
    }
    $live = ! empty( $state['live_id'] ) ? omnidome_builder_owned_post( $state['live_id'], $key ) : null;
    if ( ! $live ) {
        $live = omnidome_builder_find_post( $key, 'live' );
        if ( is_wp_error( $live ) ) {
            return $live;
        }
    }
    // Recover a publish whose HTTP response/option update was lost after the post write.
    if ( $live && 'publish' === $live->post_status && $draft &&
         ( $state['published_hash'] ?? '' ) !== ( $state['exported_hash'] ?? '' ) &&
         omnidome_builder_fingerprint( $draft ) === ( $state['draft_fingerprint'] ?? '' ) &&
         omnidome_builder_same_content( $live, $draft ) ) {
        $state['live_id'] = $live->ID;
        $state['published_hash'] = $state['exported_hash'];
        $state['live_fingerprint'] = omnidome_builder_fingerprint( $live );
    }
    $status = empty( $state['exported_hash'] ) ? 'not_exported' : 'draft_exported';
    if ( $live && ! empty( $state['published_hash'] ) && $state['published_hash'] === ( $state['exported_hash'] ?? '' ) ) {
        $status = 'published';
    }
    if ( ( ! empty( $state['draft_id'] ) && ( ! $draft || 'draft' !== $draft->post_status ||
            omnidome_builder_fingerprint( $draft ) !== ( $state['draft_fingerprint'] ?? '' ) ) ) ||
         ( ! empty( $state['live_id'] ) && ( ! $live || omnidome_builder_fingerprint( $live ) !== ( $state['live_fingerprint'] ?? '' ) ) ) ) {
        $status = 'external_changes';
    }
    return array( 'status' => $status, 'exported_hash' => $state['exported_hash'] ?? null,
        'published_hash' => $state['published_hash'] ?? null,
        'remote_id' => $live ? $live->ID : ( $draft ? $draft->ID : null ),
        'preview_url' => $draft ? get_preview_post_link( $draft ) : null,
        'live_url' => $live && 'publish' === $live->post_status ? get_permalink( $live ) : null );
}

function omnidome_builder_operation( $operation, $args ) {
    global $wpdb;
    if ( ! current_user_can( 'edit_pages' ) ||
         ( 'publish-page' === $operation && ! current_user_can( 'publish_pages' ) ) ) {
        return omnidome_builder_error( 'permission', 'Insufficient WordPress page permissions.' );
    }
    if ( empty( $args['external_id'] ) || ! preg_match( '/^[a-f0-9-]{36}$/D', $args['external_id'] ) ) {
        return omnidome_builder_error( 'input', 'Invalid external page identity.' );
    }
    // Bind remote records to both the integration user and the per-tenant/page UUID.
    $key = 'omnidome_builder_' . hash( 'sha256', get_current_user_id() . ':' . $args['external_id'] );
    $lock = 'omnidome:' . substr( hash( 'sha256', $wpdb->prefix . $key ), 0, 48 );
    if ( '1' !== (string) $wpdb->get_var( $wpdb->prepare( 'SELECT GET_LOCK(%s, 5)', $lock ) ) ) {
        return omnidome_builder_error( 'busy', 'This page is being updated. Refresh its status before retrying.' );
    }
    try {
        $state = get_option( $key, array() );
        if ( ! is_array( $state ) ) {
            return omnidome_builder_error( 'state', 'Invalid publication record.' );
        }
        $status = omnidome_builder_status( $state, $key );
        if ( is_wp_error( $status ) ) {
            return $status;
        }
        if ( 'get-publication-status' !== $operation && 'external_changes' === $status['status'] ) {
            return omnidome_builder_error( 'conflict', 'A managed draft or live page changed in WordPress. Resolve that change before exporting or publishing.' );
        }
        if ( 'upsert-page-draft' === $operation ) {
            if ( empty( $args['title'] ) || empty( $args['content'] ) ||
                 ! preg_match( '/^[a-f0-9]{64}$/D', $args['exported_hash'] ?? '' ) ||
                 strlen( $args['content'] ) > 500000 || 1 !== ( $args['export_version'] ?? 0 ) ) {
                return omnidome_builder_error( 'input', 'Invalid page export.' );
            }
            if ( ( $state['exported_hash'] ?? '' ) !== $args['exported_hash'] ) {
                $draft = ! empty( $state['draft_id'] ) ? omnidome_builder_owned_post( $state['draft_id'], $key ) : omnidome_builder_find_post( $key, 'draft' );
                if ( is_wp_error( $draft ) ) {
                    return $draft;
                }
                // Never overwrite the live page during draft export.
                $post = array( 'post_type' => 'page', 'post_status' => 'draft', 'post_author' => get_current_user_id(),
                    'post_title' => sanitize_text_field( $args['title'] ),
                    'post_excerpt' => sanitize_textarea_field( $args['excerpt'] ?? '' ),
                    'post_content' => wp_kses_post( $args['content'] ),
                    'post_name' => sanitize_title( $args['slug'] ) . '-omnidome-preview',
                    'meta_input' => array( '_omnidome_owner' => $key, '_omnidome_kind' => 'draft' ) );
                $post['meta_input']['_omnidome_exported_hash'] = $args['exported_hash'];
                $post['meta_input']['_omnidome_desired_slug'] = sanitize_title( $args['slug'] );
                $post['meta_input']['_omnidome_content_hash'] = hash( 'sha256', wp_json_encode( array(
                    $post['post_title'], $post['post_content'], $post['post_excerpt'] ) ) );
                if ( $draft ) {
                    $post['ID'] = $draft->ID;
                }
                $id = wp_insert_post( wp_slash( $post ), true );
                if ( is_wp_error( $id ) ) {
                    return $id;
                }
                $state['draft_id'] = $id;
                $state['desired_slug'] = sanitize_title( $args['slug'] );
                $state['exported_hash'] = $args['exported_hash'];
                $state['draft_fingerprint'] = omnidome_builder_fingerprint( get_post( $id ) );
            }
        } elseif ( 'publish-page' === $operation ) {
            if ( empty( $state['exported_hash'] ) || ( $args['exported_hash'] ?? '' ) !== $state['exported_hash'] ) {
                return omnidome_builder_error( 'stale', 'The reviewed export does not match the staged draft.' );
            }
            if ( ( $state['published_hash'] ?? '' ) !== $args['exported_hash'] ) {
                $draft = omnidome_builder_owned_post( $state['draft_id'], $key );
                if ( ! $draft || 'draft' !== $draft->post_status ) {
                    return omnidome_builder_error( 'draft', 'Export a draft before publishing.' );
                }
                $live = ! empty( $state['live_id'] ) ? omnidome_builder_owned_post( $state['live_id'], $key ) : null;
                $post = array( 'post_type' => 'page', 'post_status' => 'publish', 'post_author' => get_current_user_id(),
                    'post_title' => $draft->post_title, 'post_content' => $draft->post_content,
                    'post_excerpt' => $draft->post_excerpt,
                    'post_name' => $live ? $live->post_name : $state['desired_slug'],
                    'meta_input' => array( '_omnidome_owner' => $key, '_omnidome_kind' => 'live' ) );
                if ( $live ) {
                    $post['ID'] = $live->ID;
                }
                $id = wp_insert_post( wp_slash( $post ), true );
                if ( is_wp_error( $id ) ) {
                    return $id;
                }
                $state['live_id'] = $id;
                $state['published_hash'] = $args['exported_hash'];
                $state['live_fingerprint'] = omnidome_builder_fingerprint( get_post( $id ) );
            }
        } elseif ( 'get-publication-status' !== $operation ) {
            return omnidome_builder_error( 'operation', 'Unknown operation.' );
        }
        $result = omnidome_builder_status( $state, $key );
        if ( ! update_option( $key, $state, false ) && get_option( $key ) !== $state ) {
            return omnidome_builder_error( 'storage', 'Publication record could not be saved. Refresh status.' );
        }
        return $result;
    } finally {
        $wpdb->get_var( $wpdb->prepare( 'SELECT RELEASE_LOCK(%s)', $lock ) );
    }
}
