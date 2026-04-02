# Legacy Migration

## Overview

When Pro was first launched it was necessary to migrate case and user data from legacy.  This was needed both to seed
the initial data and to handle ongoing data that was updated in legacy after pro was launched.  In addition to the data
we migrated at launch there was some additional data that was migrated after (e.g. user saved cases).  This document 
describes the process, what was/wasn't migrated, and future migration considerations.

The main legacy datastore is a mongo database.  During migration each record to migrate was read from mongo, transformed
as necessary and written to the pro postgres db.  The migration logic is within the `figure1.admin.migrate` package.


## What data was/wasn't migrated

The [migration planning document](https://docs.google.com/spreadsheets/d/1pNoqMCmYQ7xGK4cD04dkJsyXZ_HqHSp1z4MGKMpxcus/edit?usp=sharing)
serves as a master list of data available from legacy and the migration status.  At the time of writing anything marked
in the column "Migrate at later date" or "NOT migrated" has not been migrated to pro, though it wasn't well maintained
after launch so some data may be inaccurate.

Some legacy data that was not yet needed exists in the legacy table but not the pro table (e.g. in `c_legacy_comment` 
but not `c_comment`). For other data that is not in postgres at all it will require reading directly from mongo - one
option is to use a path similar to `migrate_saved_cases_endpoint`.  

Some info on notable pieces of data:
 - **Image stack (aka image series)**:  cases were migrated along with data to display the image series.  The cases are
marked with `CaseState.UNSUPPORTED` so they don't appear in pro, and contain media with `MediaType.IMAGE_SERIES`
 - **Practice areas, interests**:  not migrated.  These existed in mongo under `users.expertise` and `users.interests`
respectively.  The data is stored as mesh descriptor IDs.
 - **Verification data**:  the only verification data that was migrated was if they were verified or not and their npi
number if available.  


## Migrating data before launch

This section describes how data was initially migrated from Legacy.  This code still exists for reference though is
probably too heavy for future migration needs.  Migration was driven through scheduled tasks.  The migration ran for any 
records not yet migrated and for records which were updated in legacy since the last migration. 

### Queue tables

Pending migrations to run are staged in the `q_legacy_case_queue` and `q_legacy_user_queue` tables.  Populating these
tables happened from a scheduled task but endpoints also still exist to explicitly run.  Running the task reads the 
associated data from mongo and populates the queue table with information about which records require migration. The 
migration state is managed by the columns `propagated_at` and `updated_at` - a record is migrated if `propagated_at` is 
null or if it's older than the `upated_at` date.

### Migrating data

The actual migration tasks were also triggered by scheduled tasks or started explicitly through the endpoints.  The task
looks for pending records to migrate in the queue tables and processes these one by one.  For both users and cases
the actual migration process takes care of creating records in both the legacy and pro postgres tables (e.g.
`c_legacy_case` and `c_case`).

### Locking

The tasks to populate the queue tables and run the migrations are guarded by a since deprecated locking mechanism.  They 
rely on rows in the `q_scheduled_task_lock` table which was intended to guarantee single-task operation (i.e. that
only a single instance of each task is run at once).  At the time of writing rows currently exist in this table which
would prevent any migrations from running, but if migration ever needs to be re-enabled these could be removed. 

### Forcing migration

An endpoint exists for both case and user migration that accepts a single legacy_id.  The legacy_id can be found in
the postgres legacy table. This can be used to re-run a migration for a specific record.  This was often used to handle
one off support requests or issues.
