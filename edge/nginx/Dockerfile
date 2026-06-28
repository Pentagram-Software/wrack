FROM nginx:1.27-alpine

# Remove the default config that ships with the image.
RUN rm /etc/nginx/conf.d/default.conf

# Copy the generated config.
COPY nginx.conf /etc/nginx/nginx.conf

# Nginx serves on port 80 by default; expose it.
EXPOSE 80

# Healthcheck: hit the /health endpoint we define in nginx.conf.
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD wget -qO- http://localhost/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
