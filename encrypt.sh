gpg --batch --yes --passphrase $SECRET_KEY --symmetric --cipher-algo AES256 data/sources.json
echo "✅ sources.json encrypted to sources.json.gpg"