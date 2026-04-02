#!/bin/bash
# This script in not sh compliant

function show_help {

cat << EOF

+++++++++++++++++++++++++
Syntax:
+++++++++++++++++++++++++

$0 <source> <target>
where <source> can be one of dev, qa, prod, or a snapshot name
and <target> can be one of qa, dev, staging, local or a snapshot name


+++++++++++++++++++++++++
Usage:
+++++++++++++++++++++++++

SNAPSHOTS
When a clone runs, an itermediate step is to create a database snapshot using pg_dump. The target can be
set to dump only by passing in either the literal word 'snapshot' which autogenerates a name for the snapshot, or
it can be a specific snapshot name.
Similarly, the source can also be a snapshot name instead of an environment.

For obvious reasons, the source and destination cannot both be snapshot names.

CLONING
This script clones databases from one environment to another, this is a destructive operation
for the target database, since it is forcibly dropped before the restore starts. This does not happen
until the dump completes however.

Some safeguards exist, however they primarily stop someone from cloning to a higher environment ( such as cloning
qa to prod ).

The source can be local, however the target is forced to be a snapshot in this case.


+++++++++++++++++++++++++
Implementation:
+++++++++++++++++++++++++

The tunnels are set up and torn down within the code, so unless there is an error which causes a
crash, there should be no tunnels left up. The bastion host will close them within about 5 minutes, so
this should not be an issue. If the script is run again immediately after crashing and leaving a tunnel up,
it will likely fail however as the port will not be available.

In order to minimize input, most of the secrets are pulled from SSM, this includes ssh keys which are stored
locally in the ~/.db_clone directory. Passwords for shared environments as well as database hostnames are
also pulled from ssm.
The ssm paths are:
/<environment>/database/hostname
/<environment>/database/root-password
/ssh/pro/<environment>/bastion

The database variables are populated by terraform at creation, but the ssh key needs to be added manually.

EOF

}

function look_for_snapshot {
    if [[ -d "${SNAPSHOT_ROOT}/${SOURCE}" ]]; then
        SOURCE_TYPE="SNAPSHOT"
        SNAPSHOT_PATH="${SNAPSHOT_ROOT}/${SOURCE}"
    else
      show_help
      exit 1
    fi
}

function handle_arguments() {
  if [[ $# != 2 ]]; then
    show_help
    exit;
  fi

  SOURCE=$1
  TARGET=$2
  case "$SOURCE" in
    "prod")
      echo "Source is prod"
      ;;
    "qa")
      echo "Source is qa"
      ;;
    "dev")
      echo "Source is dev"
      ;;
    "staging")
      echo "Source is staging"
      ;;
    "local")
      echo "Source is local - only valid target is snapshot"
      TARGET_TYPE="SNAPSHOT"
      ;;
    *)
      look_for_snapshot
  esac

  case "$TARGET" in
    "qa")
      echo "Target is qa"
      if [[ $SOURCE != "prod" ]]; then
        echo "QA can only accept clones from prod"
        exit 1
      fi
      ;;
    "staging")
      echo "Target is staging"
      if [[ $SOURCE != "prod" ]]; then
        echo "Staging can only accept clones from prod"
        exit 1
      fi
      ;;
    "dev")
      echo "Target is dev"
      ;;
    "local")
      echo "Target is local "
      ;;
    *)
      echo "Assuming target is a snapshot"
      TARGET_TYPE="SNAPSHOT"
  esac
}

function setup_source {
  source_hostname=$(aws ssm get-parameter --name /${SOURCE}/database/hostname --with-decryption |jq -r .Parameter.Value)
  source_password=$(aws ssm get-parameter --name /${SOURCE}/database/root-password --with-decryption |jq -r .Parameter.Value)
  aws ssm get-parameter --name /ssh/pro/${SOURCE}/bastion --with-decryption |jq -r .Parameter.Value > ${DB_CLONE_ROOT}/pro_${SOURCE}_key
  chmod 0600 ${DB_CLONE_ROOT}/pro_${SOURCE}_key
  ssh -i ${DB_CLONE_ROOT}/pro_${SOURCE}_key -N -f -M -S /tmp/${SOURCE} -L 5455:${source_hostname}:5432 ubuntu@bastion.${SOURCE}.pro.figure1.com
}

function setup_target {
  TARGET_REMOTE=0

  if [[ -n "$TARGET_HOSTNAME" ]]; then
    echo "$TARGET_HOSTNAME"
    target_hostname=$TARGET_HOSTNAME
  elif [[ $TARGET == "local" ]]; then
    target_hostname="localhost"
  else
    target_hostname=$(aws ssm get-parameter --name /${TARGET}/database/hostname --with-decryption |jq -r .Parameter.Value)
    TARGET_REMOTE=1
  fi

  if [[ -n "$TARGET_PASSWORD" ]]; then
    target_password=$TARGET_PASSWORD
  elif [[ $TARGET == "local" ]]; then
    target_password="test1234"
  else
    target_password=$(aws ssm get-parameter --name /${TARGET}/database/root-password --with-decryption |jq -r .Parameter.Value)
    TARGET_REMOTE=1
  fi

  if [[ -n "$TARGET_PORT" ]]; then
    target_port=$TARGET_PORT
  elif [[ $TARGET == "local" ]]; then
    target_port=5432
  else
    target_port=5466
  fi

  if [[ -n "$TARGET_USER" ]]; then
    target_user=$TARGET_USER
  elif [[ $TARGET == "local" ]]; then
    target_user="figure1_admin"
  else
    target_user="postgres"
  fi

  if [[ $TARGET_REMOTE == 1 ]]; then
    aws ssm get-parameter --name /ssh/pro/${TARGET}/bastion --with-decryption |jq -r .Parameter.Value > ${DB_CLONE_ROOT}/pro_${TARGET}_key
    chmod 0600 ${DB_CLONE_ROOT}/pro_${TARGET}_key
    ssh -i ${DB_CLONE_ROOT}/pro_${TARGET}_key -N -f -M -S /tmp/${TARGET} -L 5466:${target_hostname}:5432 ubuntu@bastion.${TARGET}.pro.figure1.com
  fi
}

function cleanup_hard_exit {
  echo "Caught hard stop... cleaning up"
  if [[ $TARGET_TYPE == "SNAPSHOT" ]]; then
    echo "Target was a snapshot - removing directory"
    rm -rfv ${SNAPSHOT_PATH}
  fi
  teardown
}

function teardown {
  echo "Closing ssh tunnel(s)"
  if [[ $TARGET_TYPE == "SNAPSHOT" ]]; then
    if [[ $SOURCE != "local" ]]; then
      ssh -S /tmp/${SOURCE} -O exit ${SOURCE}
    fi
  fi
  if [[ $SOURCE_TYPE == "SNAPSHOT" ]]; then
    if [[ $TARGET != "local" ]]; then
      ssh -S /tmp/${TARGET} -O exit ${TARGET}
    fi
  fi
  exit
}

function create_snapshot {
  if [[ $TARGET_TYPE == "SNAPSHOT" ]]; then
      if [[ $TARGET == "snapshot" ]]; then
        SNAPSHOT_NAME="figure1_snapshot_$(date +%Y_%m_%d_%s)"
      else
        SNAPSHOT_NAME=$TARGET
      fi
  else
    SNAPSHOT_NAME="figure1_snapshot_$(date +%Y_%m_%d_%s)"
  fi
  SNAPSHOT_PATH="$SNAPSHOT_ROOT/${SNAPSHOT_NAME}"
  mkdir -p ${SNAPSHOT_PATH}
  echo "Writing to snapshot ${SNAPSHOT_PATH}"
}

function remove_snapshot {
  echo "Removing snapshot $SNAPSHOT_NAME"
  rm -rv ~/.db_clone/.snapshots/figure1_snapshot_*
}


DB_CLONE_ROOT=~/.db_clone
SNAPSHOT_ROOT=${DB_CLONE_ROOT}/.snapshots
SOURCE_TYPE="DATABASE"
TARGET_TYPE="DATABASE"
mkdir -p ${SNAPSHOT_ROOT}

# handle commandline arguments

handle_arguments $@

trap cleanup_hard_exit SIGINT

if [[ $TARGET_TYPE == "DATABASE" ]]; then
    setup_target
fi

if [[ $SOURCE_TYPE == "DATABASE" ]]; then
    create_snapshot
    setup_source
fi


if [[ $SOURCE_TYPE == "DATABASE" ]]; then
  echo "Running Dump ..."
  PGPASSWORD=${source_password} pg_dump -d figure1 -h localhost -p 5455 -U postgres -j 10 -F d -x -c -C --if-exists -f ${SNAPSHOT_PATH}
else
  echo "Source is snapshot - skipping to restore"
fi
#

if [[ $TARGET_TYPE == "DATABASE" ]]; then
  echo "Force-dropping target ${TARGET} database - failure here is not an issue"
  #
  echo "UPDATE pg_database SET datallowconn = 'false' WHERE datname = 'figure1'; SELECT pg_terminate_backend(pid) FROM pg_stat_activity where datname = 'figure1'; DROP DATABASE figure1" | \
  PGPASSWORD=${target_password} PGPORT=${target_port} psql -h ${target_hostname} -U ${target_user} -d postgres

  echo "Restoring database..."
  PGPASSWORD=${target_password} pg_restore -d postgres -h ${target_hostname} -p ${target_port} -U ${target_user} -v -C -c ${SNAPSHOT_PATH}
else
  echo "Snapshot only, nothing to restore"
fi

teardown
