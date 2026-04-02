# D20 Mobile Backend GitHub Workflow

### Basic Repository Initialization

 1. Setup a Private Repository in Figure 1 Org
 2. Fork the Repository into your Account
 3. Checkout the repository from your fork `git clone https://github.com/<your_repo>/<repo>`
 4. Go Into Repository (Command line) `cd <your_repo>`
 5. Setup the Upstream Remote 
        If using ssh:  `git remote add upstream git@github.com:<Figure 1 org>/<your_repo>.git`
        If using https:  `remote add upstream https://github.com/<Figure 1 org>/<your_repo>.git`
 6. Verify Origin and Upstream Remotes:
 
 #### Example:

```
git remote -v
origin	https://github.com/<your githup user id>/<repo>.git (fetch)
origin	https://github.com/<your githup user id>/<repo>.git (push)
upstream	git@github.com:<Figure 1 org>/<repo>.git (fetch)
upstream	git@github.com:<Figure 1 org>/<repo>.git (push)
```

### Keeping a fork in sync with the master

 1. `git fetch upstream`
 2. `git pull upstream master`

### Git Flow

We do not commit to our shared upstreams, _**EVER**_.
We all maintain a fork in our own repositories following the open source fork / branch / feature request model.

All changes are submitted to our upstream (Figure1 repository) via a Pull Request. It's a bit of an extra step,
but should be an insignificant cognitive load for code submission and allows your team mates to experience at least
one opportunity to learn about your code changes before they are integrated to master.

All master branches on upstreams will be locked to only allow Pull Requests to merge into them.
