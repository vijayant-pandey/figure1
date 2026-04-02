## Elasticsearch

### Endpoints

`/rebuild`

The rebuild endpoint rebuilds the currently active index. The most common use for this is to rebuild the index when 
there has been a mapping change, or when there are issues with the existing index. 
When it is called, a new index in elasticsearch is created, and all case ids are pushed into the elasticsearch queue.
Then 4 workers go through the queue and index to the created index. Once complete, the index alias is switched over in 
the es_index table, and the old index is deleted in elasticsearch.

### Working with Elasticsearch

In this context, the assumption is that you are working through kibana, though curl can also be used to send commands. To
get to kibana on dev for example, simply go to `https://search.dev.pro.figure1.com`, once the page loads, look on the
left side for a wrench icon and click on that. This is the developer console. 

The general context here is to type commands on the left in the general form:
```
GET/POST/PUT/DELETE </path/to/command>
{
  <body in json format if necessary>
}
```
GET commands can be simply one line such as

```
GET /_cat/indices
```
This would return a list of indices

GET commands can also take a body such as the following search command
```
GET /6938b81d-2879-405b-a65f-49fb5f3ec893/_search
{
  "query": {
    "match_all": {}
  }
}
```

#### Listing

List indices or aliases
- `GET /_cat/indices`
- `GET /_cat/aliases`

#### Searching
Search a specific index
```
GET /6938b81d-2879-405b-a65f-49fb5f3ec893/_search
{
  "query": {
    "match_all": {}
  }
}
```
Or search by alias
```
GET /newcases/_search
{
  "query": {
    "match_all": {}
  }
}
```

Test a search result, this is what is used to execute a search from the client, the index name is replaced with the
index being searched
```
GET /newcases/_search
{
    "query": {
        "bool": {
            "minimum_should_match": 1,
            "should": [
                {
                    "match": {
                        "caption": search_string
                    }
                },
                {
                    "match": {
                        "title": search_string
                    }
                },
                {
                    "match": {
                        "mesh_terms_text": search_string
                    }
                }
            ]
        }
    }
}
```

#### Scripts

!! Note !!

Scripts are no longer used at all, however, this is a good howto for writing scripts, so I'm leaving it here

!!

All of the scripts in use are written in painless which is a domain specific language that mostly looks like java. The
most important thing to note is that the context is extremely important, the update_by_query context has access to
different operations and fields than the search context does. This topic is too large to tackle here, however right now
we are only using scripts in the update_by_query context.

Note that 
To troubleshoot scripts, you can GET the script:

```
GET /_scripts/add_case_reaction
```

If you want to change it, you can modify it and POST it back
```
POST /_scripts/add_case_reaction
{
    "script": {
      "source": """
              if (ctx._source.reactions[params.reaction].contains(params.user_uuid))
              {
              ctx.op = 'noop'
              }
              else
              {
               ctx._source.reactions[params.reaction].add(params.user_uuid);
               }
        """,
      "lang": "painless"
    }
}
```

Then make sure it works by calling it again:
```
POST /_all/_update_by_query
{
  "script": {
    "id": "add_case_reaction",
    "params": {
      "user_uuid": "221e8e94-75d0-421c-80bb-7f1113bdd111",
      "reaction": "agree"
    }
  },
  "query": {
    "term": {
      "caseUuid": {
        "value": "011ae944-77e8-459f-863a-600da2dafaaa"
      }
    }
  }
}
```
If something goes wrong, then just delete the rest_endpoints pod and it will re-write all of the scripts as part of the
initialization process.

### Case Index

#### Topics

Topics are made to be as flexible as possible. 
They are described by an entry in the topics table in the database which contains the instructions required to generate tham.
At the end, these are formulated into an a search query for elasticsearch. 


There is more detail under FeedImplementation in the Architecture folder.

#### Made For You

Made For You is known as Recommended For You externally, though the code references still use MFY.
This is essentially a search filtered by the users specialties and interests. 

#### Search

Search for cases and users are one of the few endpoints that is a request/response endpoint.
It basically just puts the term in a search and returns the results.

#### Trending

In order to generate usable trending data, we have two different fields for each event that we want to use for trending.
The first field, prefixed by latest_, is a list of maps, each map contains a uuid, this is a unique identifier for the
event, for comments, it would be the comment_uuid, for case reactions, it would be the user_uuid, and an updated_at date
field which indicates the time of this event.
The second field, prefixed by score_, is an ordered list of dates taken from the latest_ list. The order is from most 
recent to oldest, and is capped at 20 entries. This field is generated only by elasticsearch and is completely 
regenerated on each update.

Once we have the data in place, we are able to use function_score against each of the score_ fields to modify the
relevance in searches.


#### Example: Adding trending data to a case reaction

The exact names may change, however this code lives in figure1.common.elasticsearch.methods.py and up to date script
names can be found there.

When we receive a rest request adding a reaction, first the database is updated, then we add the reaction itself to the
 appropriate list in elasticsearch. Only the elasticsearch portion is covered here.

First, add the reaction to elasticsearch. For reactions specifically there are 3 fields, agree, clinically_useful,
 and informative, adding a reaction means the user_uuid who reacted is added to the appropriate list. 

Next, the user_uuid and the updated_at date is added to the latest_reactions list of maps. 

Finally, the trend_field script is called, This creates a new field, called score_reactions which is simply a sorted 
 list of dates taken from latest_reactions. This list is now used to modify the score based on date-based decay. 

In detail, the elasticsearch code looks as follows:

* Add the case reaction
```
POST /_all/_update_by_query
{
        "script": {
            "id": "add_case_reaction",
            "params": {
              "user_uuid": "221e8e94-75d0-421c-80bb-7f1113bdd111",
              "reaction": "agree"
            }
        },
        "query": {
            "term": {
                "caseUuid": {
                    "value": "011ae944-77e8-459f-863a-600da2dafaaa"
                }
            }
        }
    }
```

This uses the add_case_reaction script defined as:

```
POST /_scripts/add_case_reaction
{        "script": {
            "source": """
            if (ctx._source.reactions[params.reaction].contains(params.user_uuid))
            {
            ctx.op = 'noop'
            }
            else
            {
             ctx._source.reactions[params.reaction].add(params.user_uuid);
             }
            """,
            "lang": "painless"
        }
}
```
* Update latest_reactions
```
POST /_all/_update_by_query?wait_for_completion=true&refresh=true
{
  "script": {
    "id": "add_latest",
    "params": {
      "updated_at": "2019-01-01",
      "uuid": "fff865f0-f0f3-4eae-af7c-5f0ed5ce9bfd",
      "target_field": "latest_reactions"
    }
  },
    "query": {
    "term": {
      "caseUuid": {
        "value": "fff865f0-f0f3-4eae-af7c-5f0ed5ce9bfd"
      }
    }
  }
}
```

The add_latest script is defined as:
```
POST /_scripts/add_latest
{
  "script": {
    "source": """
            if (ctx._source[params.target_field].contains(params.uuid))
            {
            ctx.op = 'noop'
            }
            else
            {
             Map m = ['updated_at':params.updated_at, 'uuid': params.uuid];
             int idx = -1;
             for (item in ctx._source[params.target_field])
             {
               if ( item['uuid'] == params.uuid ){
                 idx = ctx._source[params.target_field].indexOf(item);
               }
             }
             if (idx >= 0){
               ctx._source[params.target_field].remove(idx);
             }
             ctx._source[params.target_field].add(m);
             }
""",
    "lang": "painless"
  }
}
```
* Finally, the trend field is generated, called score_reactions in this case:

```
POST /_all/_update_by_query?wait_for_completion=true&refresh=true
{
  "script": {
    "id": "trend_field",
    "params": {
      "source_field": "latest_reactions",
      "target_field": "score_reactions"
    }
  },
    "query": {
    "term": {
      "caseUuid": {
        "value": "fff865f0-f0f3-4eae-af7c-5f0ed5ce9bfd"
      }
    }
  }
}
```

This script is defined as:
```
POST /_scripts/trend_field
{
  "script": {
    "source": """
    if (ctx._source.containsKey(params.source_field)) {
      ArrayList dl = [];
      for (int j=0; j<ctx._source[params.source_field].length; j++) {
        dl.add(ctx._source[params.source_field][j].updated_at);
      }
      Collections.reverse(dl);
      if (ctx._source.containsKey(params.target_field)){
        ctx._source.remove(params.target_field);
      } 
      if ( dl.length > 20 ){
        ctx._source[params.target_field] = dl.subList(0,19);
      } else{
        ctx._source[params.target_field] = dl;
      }
    }
""",
    "lang": "painless"
  }
}
```