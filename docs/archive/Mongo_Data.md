## Importing mongo data

If you are developing against the prequel app, at some point you are going to want to pull data from mongo. While the solution that we have is imperfect, we are able to easily import tables. How long this takes depends largely on the size of the table, but at minimum, you can assume about 1min per GB.

There are dumps of the staging data located in S3 inside the figure1-platform-test-bucket/mongo. In this bucket, there is a directory called f1 which contains the complete dump of all the collections in staging, each collection is represented by a bson file which is the data, and a metadata.json file which is the schema. There is also a file called figure1.tar.gz which is the dump of mongodb in its entirety. If you want the whole database, this is the one you should download.

Download both files for a table you want, and in the root directory of the f1-pro-backend repo, create a directory called mongo-import, and copy those files in. The mongo-import directory is created if it does not exist when the dev environment starts, but you want to have your files in before the environment starts.

There is no limit to how many tables you can restore at a time, mongo will just work its way through them.

When the mongo instance starts, the init container will perform the import. The mongo-restore command will drop any collections that it is about to import and will not create any indexes. It does not drop the database however, so as long as you remove both the bson file and the metadata file from the mongo-import directory before restarting, those collections are safe.
