# Overlay for the email-intelligence change: copies only the files listed in deploy-email-intelligence.sh over a running image.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY services /app/services
