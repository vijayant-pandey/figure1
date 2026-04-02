# FAQ

Please search below if you have a question in the event that it has been answered in the form of an example of code.

## How do I update my local k8s cluster with the latest and greatest code from master (without PyCharm involved)?

You need to grab the latest code from master, rebuild your development docker container, and redeploy services to k8s:

1. Run `dev/stop-dev.sh` to shut down everything on the cluster (including the database and your dev docker container). 
You want to do this first because it takes a while for the cluster to shut itself down, so you can do the following 
steps while you wait.
1. Run `git pull` to grab the latest code from master.
1. Run `dev/build-dev.sh` to rebuild your docker container. Go use the bathroom or fill up your coffee and let this
finish.
1. Run `kubectl get pods` periodically until you see that figure1 pods have terminated
1. When the docker container rebuild has finished _*AND*_ `kubectl get pods` is showing no figure1-services run
`dev/start-dev.sh` to bring the database and the development docker container up
1. Run `dev/start-backend.sh` to bring the (updated) backend back online.

## I used to be able to "see" the database in PyCharm when everything was in docker compose, but now that we're using Kubernetes it keeps asking me for the password that does not work. What's wrong?

This is a particularly _**nasty**_ PyCharm bug. If you just try to open the existing entry, fiddle with the parameters and click `Test Connection` it will tell you that 
everything works, but when you try to refresh the schema or execute queries they will ask you for a password, which will
always fail.

To fix this, you need to actually blow away the database link in PyCharm and re-add it as follows:

1. On the Database widget, right click on the PostgreSQL database and select `Remove`
1. Click the `+` symbol, then select `Data Source` --> `PostgreSQL`
1. Set `Host` to `localhost`
1. Set `database` to `figure1`
1. Set `user` to `figure1_admin`
1. Set `password` to `test1234`
1. Sett `port` to `31001`
1. Click `Test Connection` and make sure it works
1. Click `Apply` and close the dialog, and you should see the figure1 once again. Your queries in Database 
consoles should work again, though the first time they will complain as they adjust to the updated settings.

## How do I reset my development container environment to a clean state?
Either:

1. Run `kubectl delete -f k8s/dev/figure1-dev-environment.yaml`
1. Run `kubectl apply -f k8s/dev/figure1-dev-environment.yaml`
1. Right click on the project root, then click `Deployment-->Upload to figure1-backend` to copy the latest source to the 
remote container

**-OR-**

1. Run `kubectl delete -f k8s/dev/d20-dev-environment.yaml`
1. Run `dev/build-dev.sh`, which rebuilds the dev image with whatever you have in <project root> included. 
1. Run `kubectl apply -f k8s/dev/d20-dev-environment.yaml`

## How to blow away my database and start over with a clean slate?

1. `dev/stop-dev.sh` to shut down any backend containers, and the PostgreSQL database
1. `rm -rf database` to blow away the database
1. `dev/start-dev.sh` to bring PostgreSQL back up (and create a clean database)
1. Run d20/db/d20_database.py to create all of the tables required by the backend
1. `dev/start-backend.sh` to launch all backend services against the clean database
 
## I'm getting an ssh error when trying to access my local k8s dev environment

Are you are seeing this error when trying to ssh to your local k8s dev environment?

```Unable to negotiate with ::1 port 32766: no matching key exchange method found. Their offer: diffie-hellman-group1-sha1```

If so, the issue is that OpenSSH version 7. SHA1 is weak, so support for it has been removed. Which is fine, but our dev
k8s environment is still using RSA/SHA1. So you'll need to re-enable SHA1 to be able to connect from the command line.
To do that do the following:

1. `sudo nano /etc/ssh/ssh_config`  (you can also use vi or whatever other text editor you like)
1. Locate the line `#   MACs hmac-md5,hmac-sha1,umac-64@openssh.com,hmac-ripemd160` and remove the Hash/Pound sight from the beginning.
1. Locate the line `#   Ciphers aes128-ctr,aes192-ctr,aes256-ctr,aes128-cbc,3des-cbc` and remove the Hash/Pound sight from the beginning.
1. Paste the following at the end of the file:
    ```
    HostkeyAlgorithms ssh-dss,ssh-rsa
    KexAlgorithms +diffie-hellman-group1-sha1
    ```
    
Once you save the file, the changes will take effect immediately and you should be able to log into your local k8s dev 
environment. For more on this fix: https://www.petenetlive.com/KB/Article/0001245

## I cannot clone the database
There are a various issues that may prevent you running `database_clone.sh` successfully. 
* Make sure you have AWS cli access and have correct env setup. You need these at minimum
````shell script
export AWS_ACCESS_KEY_ID=
export AWS_SECRET_ACCESS_KEY=
export AWS_DEFAULT_REGION=us-east-1
export AWS_REGION=us-east-1
````
* If you encounter an error about wrong python version, it could be because a python@2 was installed via brew before. Try follow this [instruction](https://stackoverflow.com/questions/60229970/aws-cli-errorrootcode-for-hash-md5-was-not-found#:~:text=To%20fix%20this%2C,to%20python2%20came%20with%20macOS.&text=if%20you%20run%20aws%20%2D%2D,to%20python3%20instead%20of%20python2%20.) to fix it.
* You need to use `pg_dump@12`. Setup it as
    * `brew install postgresql@12`
    * `brew link -n postgresql@12`
* If see error messages like `Offending ED25519... ECDSA host key for bastion.dev.pro.figure1.com has changed...`. Delete the `bastion.dev.pro.figure1.com...` line in `~/.ssh/known_hosts` and try again