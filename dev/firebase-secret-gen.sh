#!/usr/bin/env bash

if [ "$#" -ne 1 ]; then
    echo "$#"
    echo "usage:"
    echo "Use this script to generate a secret for firebase using the json file that was downloaded from google as the admin.json file"
    echo "firebase-secret-gen.sh admin.json"
    exit
fi

eval `jq -r 'to_entries | map(.key |= ( "FIREBASE_" + . | ascii_upcase )) | map(.value |= @base64) | map( "export " + .key + "=" + .value + ";")|.[]' ${1}`

cat <<EOF
apiVersion: v1
data:
  FIREBASE_CLIENT_EMAIL: ${FIREBASE_CLIENT_EMAIL}
  FIREBASE_CLIENT_ID: ${FIREBASE_CLIENT_ID}
  FIREBASE_CLIENT_x509_CERT_URL: ${FIREBASE_CLIENT_X509_CERT_URL}
  FIREBASE_PRIVATE_KEY: ${FIREBASE_PRIVATE_KEY}
  FIREBASE_PRIVATE_KEY_ID: ${FIREBASE_PRIVATE_KEY_ID}
kind: Secret
metadata:
  creationTimestamp: null
  name: firebase

EOF
