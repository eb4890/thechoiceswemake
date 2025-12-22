#!/bin/bash

# Configuration
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

domains=($DOMAIN)
rsa_key_size=4096
data_path="./certbot"
email="$EMAIL" # Adding a valid address is strongly recommended
staging=0 # Set to 1 if you're testing your setup to avoid hitting rate limits

if [ -z "$DOMAIN" ]; then
    echo "DOMAIN not set. Nginx will run in HTTP-only mode."
    exit 0
fi

# Use the first domain for the certificate directory path
export CERT_DOMAIN="${domains[0]}"
export DOMAIN

if [ ! -e "$data_path/conf/options-ssl-nginx.conf" ] || [ ! -e "$data_path/conf/ssl-dhparams.pem" ]; then
  echo "### Downloading recommended TLS parameters ..."
  mkdir -p "$data_path/conf"
  curl -s https://raw.githubusercontent.com/certbot/certbot/master/certbot-nginx/certbot_nginx/_internal/tls_configs/options-ssl-nginx.conf > "$data_path/conf/options-ssl-nginx.conf"
  curl -s https://raw.githubusercontent.com/certbot/certbot/master/certbot/certbot/ssl-dhparams.pem > "$data_path/conf/ssl-dhparams.pem"
  echo
fi

echo "### Creating dummy certificate for $CERT_DOMAIN ..."
path="/etc/letsencrypt/live/$CERT_DOMAIN"
mkdir -p "$data_path/conf/live/$CERT_DOMAIN"
docker-compose run --rm --entrypoint "\
  openssl req -x509 -nodes -newkey rsa:$rsa_key_size -days 1\
    -keyout '$path/privkey.pem' \
    -out '$path/fullchain.pem' \
    -subj '/CN=localhost'" certbot
echo

echo "### Starting nginx ..."
# Pass CERT_DOMAIN to nginx as well if needed, but we'll use a template
docker-compose up --force-recreate -d nginx
echo

echo "### Deleting dummy certificate for $CERT_DOMAIN ..."
docker-compose run --rm --entrypoint "\
  rm -rf /etc/letsencrypt/live/$CERT_DOMAIN" certbot
echo

echo "### Requesting Let's Encrypt certificate for $domains ..."
#Join $domains to -d domain.com -d www.domain.com
domain_args=""
for domain in "${domains[@]}"; do
  domain_args="$domain_args -d $domain"
done

# Select appropriate email arg
case "$email" in
  "") email_arg="--register-unsafely-without-email" ;;
  *) email_arg="--email $email" ;;
esac

# Enable staging mode if needed
if [ $staging != "0" ]; then staging_arg="--staging"; fi

docker-compose run --rm --entrypoint "\
  certbot certonly --webroot -w /var/www/certbot \
    $staging_arg \
    $email_arg \
    $domain_args \
    --rsa-key-size $rsa_key_size \
    --agree-tos \
    --force-renewal" certbot
echo

echo "### Enabling SSL configuration ..."
cat ./nginx/ssl.conf.template | envsubst '$DOMAIN $CERT_DOMAIN' > ./nginx/conf/ssl.conf

echo "### Reloading nginx ..."
docker-compose exec nginx nginx -s reload
