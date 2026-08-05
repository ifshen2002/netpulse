FROM nginx:1.27-alpine

# Generate self-signed certificate for demo use.
# In production, replace with Let's Encrypt or a real CA-signed certificate.
RUN apk add --no-cache openssl \
    && mkdir -p /etc/nginx/certs \
    && openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
       -keyout /etc/nginx/certs/server.key \
       -out /etc/nginx/certs/server.crt \
       -subj "/C=SG/ST=SG/L=Singapore/O=NetPulse/CN=localhost" \
    && apk del openssl

COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80 443

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -qO- http://localhost:80/api/health || exit 1
