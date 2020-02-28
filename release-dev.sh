#!/bin/bash
set -x

USER=artsalliancemedia
REPO=thunderstorm-library
PACK=thunderstorm
TAG=$(python setup.py --version).$(git rev-parse --short HEAD)

git remote set-url origin git@github.com:${USER}/${REPO}.git

if git log --oneline --no-merges -1 | grep -i "\[release-dev\]"
then
    git tag -a v${TAG} -m "release dev version v${TAG}"
    git push origin v${TAG}
fi

exit 0;
