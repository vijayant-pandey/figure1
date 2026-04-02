## 
There is a limited number of indexes available directly from the public internet
that are intended to be used for things like type-ahead searches. The data
that is considered public, though we do have authentication in place for it.

###Firestore Configuration

Inside the configuration collection of firestore(configurationDB),  there is a key
called ElasticSearchConfig which holds configuration to connect to elasticsearch. 

The elasticsearchAuth key contains the the keys required to authenticate.

The expiration says when the key expires in seconds since epoch. This is 1200 seconds from 
creation time.

The access_token is the bearer token required to authenticate.

The elasticsearchCloudId is a base64 encoded string that can be passed to most elasticsearch
clients for the connection information. This should not change.

The elasticsearch javascript sdk is pretty stupid in how it handles the cloud id. Essentially,
if you use a cloud id, you can only use a username/password. Since we don't use a user/password, 
the best idea is to extract the data out of the cloud id and use it directly.

```javascript
const getElasticSearchEndpoint = (cloudId) => {
    if (!isEmpty(cloudId)) {
      const cloudUrls = Buffer.from(split(cloudId, ":")[1], "base64")
        .toString()
        .split("$");
      ElasticSearchConfig.endpointUrl = `https://${cloudUrls[1]}.${cloudUrls[0]}`;
    }
    return null
  }
```

Now, all you have to do is call the function with the cloud id and get the url back. The last step
here is adding the bearer token authorization. This is covered in the next section.

###Authentication and Configuration

The elasticsearch credentials are created as oauth2 credentials, but only the access_key is 
populated, this key expires every 20 minutes. The expiration key is the utc time in seconds from
epoch of the expiry time. A new key is written every 5 minutes, but existing keys remain valid
until the expiry time

The key needs to be used in an Authorization header as a Bearer token. The format for this is
```
Authorization: Bearer <access_token>
```

This header must accompany every request to elasticsearch. 

###Indexes

There are currently two indexes that can be searched with this authentication, the public_search_terms,
and public_specialty. 
The public_search_terms index consists solely of data that is used for search completion suggestions.

The public_specialty index contains all of the specialties and is stored in such a way that you can
do completions that are only relevant to the context you are in. 