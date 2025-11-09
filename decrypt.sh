#!/bin/bash
gpg --quiet --batch --yes --decrypt --passphrase $SECRET_KEY data/sources.json.gpg > data/sources.json
echo "✅ .env decrypted"