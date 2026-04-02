#!/bin/bash
version=$1
text=$2
hash=$3
repo_full_name=Figure1/f1-pro-backend
token=$(git config --local github.token)
if [[ (-z $version) || ( $version != rc* && $version != dev* && $version != qa* ) ]]
then
  echo "A version is required and should follow Semantic Versioning Major.Minor.Patch"
  echo "Dev, QA and Staging builds are required to start with 'dev' ex: dev1.0.1 or 'rc' ex: rc1.0.1 or 'qa' ex: qa1.0.1"
fi
if [ -z "$text" ]
then
  echo "Please provide a simple message for the release description"
fi
if [ -z "$hash" ]
then
  echo "A valid commit hash is required or no release can be generated"
fi
if [[ (-z "$version") || (-z "$text") || (-z "$hash") || ( $version != rc* && $version != dev*  && $version != qa* ) ]]
then
  echo "All parameters were required, exiting"
  exit 1
fi
generate_post_data()
{
  cat <<EOF
{
  "tag_name": "$version",
  "target_commitish": "$hash",
  "name": "$version",
  "body": "$text",
  "draft": false,
  "prerelease": true
}
EOF
}
echo "Create release $version for repo: $repo_full_name commit hash: $hash"
echo "Posting to API Endpoint: https://api.github.com/repos/$repo_full_name/releases?access_token=<hidden>"
echo "With Data: $(generate_post_data)"
curl --data "$(generate_post_data)" -H "Authorization: token ${token}" "https://api.github.com/repos/$repo_full_name/releases"
