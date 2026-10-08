<?php
// Minimal WordPress API fixture: execute the real companion callbacks with persistent in-memory state.
define( 'ABSPATH', __DIR__ );
$posts = array(); $meta = array(); $options = array(); $abilities = array(); $hooks = array();
$user = 1; $may_publish = true; $writes = 0; $fail_option = false; $may_edit = true; $lock_available = true;
class WP_Error {
    public $code; public $message;
    function __construct( $code, $message ) { $this->code = $code; $this->message = $message; }
}
class FixtureDB {
    public $prefix = 'wp_';
    function prepare( $query, ...$args ) { return $query; }
    function get_var( $query ) { global $lock_available; return $lock_available ? '1' : '0'; }
}
$wpdb = new FixtureDB();
function add_action( $hook, $callback ) { global $hooks; $hooks[$hook][] = $callback; }
function wp_register_ability_category( $name, $args ) {}
function wp_register_ability( $name, $args ) { global $abilities; $abilities[$name] = $args; }
function current_user_can( $capability, ...$args ) {
    global $may_publish, $may_edit;
    return $may_edit && ( 'publish_pages' !== $capability || $may_publish );
}
function get_current_user_id() { global $user; return $user; }
function get_bloginfo( $field ) { return 'Fibre ISP'; }
function is_wp_error( $value ) { return $value instanceof WP_Error; }
function wp_json_encode( $value ) { return json_encode( $value ); }
function sanitize_text_field( $value ) { return trim( strip_tags( $value ) ); }
function sanitize_textarea_field( $value ) { return trim( strip_tags( $value ) ); }
function sanitize_title( $value ) { return trim( strtolower( preg_replace( '/[^a-zA-Z0-9-]/', '-', $value ) ), '-' ); }
function wp_kses_post( $value ) { return preg_replace( '#<script[^>]*>.*?</script>#s', '', $value ); }
function wp_slash( $value ) { return $value; }
function get_post( $id ) { global $posts; return isset( $posts[$id] ) ? clone $posts[$id] : null; }
function get_post_meta( $id, $key, $single ) { global $meta; return $meta[$id][$key] ?? ''; }
function get_posts( $query ) {
    global $posts, $meta;
    return array_values( array_filter( $posts, function ( $post ) use ( $query, $meta ) {
        if ( ! in_array( $post->post_status, $query['post_status'], true ) ) return false;
        foreach ( $query['meta_query'] as $match ) {
            if ( ( $meta[$post->ID][$match['key']] ?? '' ) !== $match['value'] ) return false;
        }
        return true;
    } ) );
}
function get_option( $key, $default = false ) { global $options; return $options[$key] ?? $default; }
function update_option( $key, $value, $autoload ) {
    global $options, $fail_option;
    if ( $fail_option ) { $fail_option = false; return false; }
    $changed = ! isset( $options[$key] ) || $options[$key] !== $value;
    $options[$key] = $value;
    return $changed;
}
function wp_insert_post( $post, $error ) {
    global $posts, $meta, $writes;
    $id = $post['ID'] ?? count( $posts ) + 1;
    $writes++;
    $meta[$id] = $post['meta_input'];
    unset( $post['meta_input'] );
    $post['ID'] = $id;
    $posts[$id] = (object) $post;
    return $id;
}
function get_preview_post_link( $post ) { return 'https://isp.example/?page_id=' . $post->ID . '&preview=true'; }
function get_permalink( $post ) { return 'https://isp.example/' . $post->post_name; }
function check( $condition, $label ) {
    if ( ! $condition ) { fwrite( STDERR, 'FAIL: ' . $label . "\n" ); exit( 1 ); }
}
require __DIR__ . '/../omnidome-builder/omnidome-builder.php';
foreach ( $hooks as $callbacks ) foreach ( $callbacks as $callback ) $callback();
check( count( $abilities ) === 4, 'four abilities registered' );
$id = '12345678-1234-1234-1234-123456789abc';
$draft = array( 'external_id' => $id, 'exported_hash' => str_repeat( 'a', 64 ), 'export_version' => 1,
    'title' => 'Fibre', 'slug' => 'fibre', 'excerpt' => 'Fast', 'content' => '<p>100 Mbps</p>' );
$export = $abilities['omnidome/upsert-page-draft']['execute_callback'];
$publish = $abilities['omnidome/publish-page']['execute_callback'];
$status = $abilities['omnidome/get-publication-status']['execute_callback'];
$result = $export( $draft );
check( $result['status'] === 'draft_exported' && count( $posts ) === 1, 'initial draft' );
$draft_id = $result['remote_id'];
$initial_writes = $writes;
$export( $draft );
check( $writes === $initial_writes, 'idempotent export' );
check( is_wp_error( $publish( array( 'external_id' => $id, 'exported_hash' => str_repeat( 'b', 64 ) ) ) ), 'stale hash rejected' );
$may_publish = false;
check( ! $abilities['omnidome/publish-page']['permission_callback']( array() ), 'publish capability checked' );
check( is_wp_error( $publish( array( 'external_id' => $id, 'exported_hash' => $draft['exported_hash'] ) ) ), 'callback also checks publish capability' );
$may_publish = true;
$result = $publish( array( 'external_id' => $id, 'exported_hash' => $draft['exported_hash'] ) );
check( $result['status'] === 'published' && count( $posts ) === 2, 'publish creates separate live page' );
$live_id = $result['remote_id'];
$initial_writes = $writes;
$publish( array( 'external_id' => $id, 'exported_hash' => $draft['exported_hash'] ) );
check( $writes === $initial_writes, 'idempotent publication' );
$draft['exported_hash'] = str_repeat( 'b', 64 ); $draft['content'] = '<p>200 Mbps</p>';
$export( $draft );
check( $posts[$live_id]->post_content === '<p>100 Mbps</p>', 're-export leaves live content unchanged' );
$posts[$live_id]->post_content = '<p>Edited directly in WordPress</p>';
check( $status( array( 'external_id' => $id ) )['status'] === 'external_changes', 'external live edit detected' );
check( is_wp_error( $publish( array( 'external_id' => $id, 'exported_hash' => $draft['exported_hash'] ) ) ), 'external live edit blocks publish' );
$posts[$live_id]->post_content = '<p>100 Mbps</p>';
$fail_option = true;
check( is_wp_error( $publish( array( 'external_id' => $id, 'exported_hash' => $draft['exported_hash'] ) ) ), 'lost publication-record save reported' );
check( $status( array( 'external_id' => $id ) )['status'] === 'published', 'lost publish recovered by status' );
$draft['exported_hash'] = str_repeat( 'c', 64 ); $draft['content'] = '<p>300 Mbps</p>';
$fail_option = true;
check( is_wp_error( $export( $draft ) ), 'lost export-record save reported' );
$recovered = $status( array( 'external_id' => $id ) );
check( $recovered['exported_hash'] === $draft['exported_hash'] && $recovered['status'] === 'draft_exported', 'lost export recovered' );
$posts[$draft_id]->post_content = 'Unreviewed WordPress edit';
check( is_wp_error( $publish( array( 'external_id' => $id, 'exported_hash' => $draft['exported_hash'] ) ) ), 'modified staged draft rejected' );
$new_draft = $draft;
$new_draft['external_id'] = 'abcdefab-1234-1234-1234-123456789abc';
$fail_option = true;
check( is_wp_error( $export( $new_draft ) ), 'initial export-record failure reported' );
$initial_writes = $writes;
$recovered = $status( array( 'external_id' => $new_draft['external_id'] ) );
check( $recovered['exported_hash'] === $new_draft['exported_hash'], 'initial orphan draft recovered' );
$export( $new_draft );
check( $writes === $initial_writes, 'initial orphan draft not duplicated on retry' );
$user = 2;
check( $status( array( 'external_id' => $id ) )['status'] === 'not_exported', 'other integration user cannot access pages' );
$lock_available = false;
check( is_wp_error( $export( $draft ) ), 'lock failure refuses mutation' );
echo "Companion workflow, idempotency, conflict, permissions, and recovery checks passed.\n";
