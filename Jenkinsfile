#!/usr/bin/env groovy

def registry = '886366864302.dkr.ecr.eu-west-1.amazonaws.com'
def user = 'artsalliancemedia'
def repo = 'thunderstorm-library'

node('aam-identity-prodcd') {
    properties([
        [
            $class: 'GithubProjectProperty',
            displayName: 'TS Lib',
            projectUrlStr: "https://github.com/${user}/${repo}/"
        ]
    ])

    def COMPOSE_PROJECT_NAME = getDockerComposeProject()

    stage('Checkout') {
        checkout scm
    }

    try {
        // CODACY_PROJECT_TS_LIB_TOKEN is a global set in jenkins
        stage('Test') {
            withEnv([
              "REGISTRY=${registry}"
            ]) {
              sh 'docker-compose up -d'
              sh 'sleep 5'
              parallel 'python36': {
                withEnv(["COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME}36"]) {
                  sh "docker-compose run -e CODACY_PROJECT_TOKEN=${env.CODACY_PROJECT_TS_LIB_TOKEN} -e PYTHON_VERSION=36 python36 make install test codacy"
                  junit 'results-36.xml'
                }
              }, 'python37': {
                withEnv(["COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME}37"]) {
                  sh "docker-compose run -e CODACY_PROJECT_TOKEN=${env.CODACY_PROJECT_TS_LIB_TOKEN} -e PYTHON_VERSION=37 python37 make install test codacy"
                  junit 'results-37.xml'
                }
              }, 'compatibility-marshmallow-2.X': {
                withEnv(["COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME}36compat"]) {
                  sh "docker-compose run -e CODACY_PROJECT_TOKEN=${env.CODACY_PROJECT_TS_LIB_TOKEN} -e PYTHON_VERSION=36 -e COMPAT=compat -e DB_NAME=test_auth_lib_py36_compat python36 make install compat test codacy"
                  junit 'results-36compat.xml'
                }
              }
              sh 'docker-compose down'
            }
        }

        // master or release/* branch
        def is_release = isRelease()

        if (is_release) {
            def version = getVersion()
            def tag = "v${version}"
            stage('Create Git Tag') {
                withEnv([
                    "GITHUB_TOKEN=${env.GITHUB_TOKEN}"
                ]) {
                    sh "git remote set-url origin git@github.com:${user}/${repo}.git"
                    sh "git tag -f ${tag}"
                    sh "git push --tags"
                }
            }
            // master branch builds are pushed to Github
            if (env.BRANCH_NAME == 'master') {
                stage('Create Github Release') {
                    withEnv([
                        "GITHUB_TOKEN=${env.GITHUB_TOKEN}",
                    ]) {
                        sh 'sudo chmod -R 777 thunderstorm_library.egg-info/'
                        sh "make dist"
                        sh "grelease owner=${user} repo=${repo} filename='dist/thunderstorm-library-${version}.tar.gz' tag=${tag}"
                    }
                }

                stage("Changelog") {
                    description = gitChangelog returnType: 'STRING',
                                gitHub: [api: 'https://api.github.com/repos/artsalliancemedia/thunderstorm-library', issuePattern: '', token: env.GITHUB_TOKEN],
                                from: [type: 'REF', value: 'master'],
                                to: [type: 'REF', value: env.BRANCH_NAME],
                                template: prTemplate()
                    echo "### Changelog ###"
                    echo "${description}"
                    echo "### Changelog ###"
                }
            }
        }

    } catch (err) {
        junit 'results-*.xml'
        error 'Thunderstorm library build failed ${err}'

    } finally {
        sh 'docker-compose down'
    }
}

def getDockerComposeProject() {
    return sh(
        script: "basename `pwd` | sed 's/^[^a-zA-Z0-9]*//g'",
        returnStdout: true
    ).trim()
}

def prTemplate() {
  def tp = readFile 'CHANGELOG.md'
  return tp.trim()
}

def isRelease() {
    if (env.BRANCH_NAME == "master")
        return true
    return env.BRANCH_NAME.startsWith("release/")
}

def getVersion() {
    if (env.BRANCH_NAME == "master")
        return sh(script: "make version", returnStdout: true).trim()
    return sh(script: "VERSION_SUFFIX=b${env.BUILD_NUMBER} make version", returnStdout: true).trim()
}
