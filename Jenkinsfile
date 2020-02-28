#!/usr/bin/env groovy

def user = 'artsalliancemedia'
def repo = 'thunderstorm-library'

node('aam-identity-prodcd') {
    properties([
        [
            $class: 'HudsonNotificationProperty',
            endpoints: [[
                event: 'all',
                format: 'JSON',
                loglines: 0,
                protocol: 'HTTP',
                timeout: 30000,
                url: 'https://webhooks.gitter.im/e/953b1e47e601cbf09ff8']]
        ],
        [
            $class: 'GithubProjectProperty',
            displayName: 'TS Lib',
            projectUrlStr: 'https://github.com/artsalliancemedia/thunderstorm-library/'
        ]
    ])

    def COMPOSE_PROJECT_NAME = getDockerComposeProject()

    stage('Checkout') {
        checkout scm
    }

    try {
        def registry = '886366864302.dkr.ecr.eu-west-1.amazonaws.com'
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

        // determine if release should be pushed: the most recent commit must contain string "[release]"
        def is_release = sh (script: 'git log --oneline --no-merges -1 | grep -q \'\\[release\\]\'', returnStatus: true)

        // master branch builds are pushed to Github
        if (env.BRANCH_NAME == 'master') {

            stage('Create Github Release') {
                // GITHUB_TOKEN is a global set in jenkins
                    withEnv([
                        "GITHUB_TOKEN=${env.GITHUB_TOKEN}",
                    ]) {
                        // create distribution
                        sh 'sudo chmod -R 777 thunderstorm_library.egg-info/'
                        sh "make dist"
                        sh "./script/release.sh '${user}' '${repo}'"
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
        if (env.BRANCH_NAME.matches("feature(.*)")){
            stage('release dev') {
                  withEnv([
                      "GITHUB_TOKEN=${env.GITHUB_TOKEN}",
                  ]) {
                    sh './release-dev.sh'
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
  def template = readFile 'CHANGELOG.md'
  // don't forget to trim or you'll get a newline in the string
  return template.trim()
}
