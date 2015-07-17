#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# """ regarding git-flow """
import nacl.gitlabapi as api
from nacl.helper import color
from nacl.helper import query_yes_no
import nacl.git as git
import sys
import pprint


class NaclFlow(object):

    def __init__(self):
        self.api = api.GitLapApiCall()

    def get_all_issues(self, all=None):
        """ Gets all issues of a project """

        issues = self.api.get_all_issues()

        if issues:
            for issue in issues:
                if not all and issue['state'] == 'closed':
                    continue
                print(color('INFO', "TITLE: " + issue['title']))
                print(color('GREEN', "ID: " + str(issue['iid'])))
                print(color('GREEN', "WHAT: " + issue['description']))
                print(color('GREEN', "STATE: " + issue['state']))
                print(color('INFO', "AUTHOR: " + issue['author']['name']))
                if issue['assignee']:
                    print(color('GREEN', "ASSIGNEE: " + issue['assignee']['name']))
                print("-") * 80
        else:
            print(color('INFO', 'No issues found'))

    def get_my_issues(self, all=None):
        """ List all my open issues """
        issues = self.api.get_my_issues()

        if issues:
            for issue in issues:
                if not all and issue['state'] == 'closed':
                    continue

                project = self.api.getproject(issue['project_id'])

                print(color('INFO', "TITLE: " + issue['title']))
                print(color('GREEN', "ID: " + str(issue['iid'])))
                print(color('GREEN', "URL: " + project['web_url']))
                print(color('BOLD', "REPO: " + project['description']))
                print(color('GREEN', "WHAT: " + issue['description']))
                print(color('GREEN', "STATE: " + issue['state']))
                print(color('INFO', "AUTHOR: " + issue['author']['name']))
                if issue['assignee']:
                    print(color('GREEN', "ASSIGNEE: " + issue['assignee']['name']))
                print("-") * 80
        else:
            print(color('INFO', 'No issues found'))

    def edit_issue(self, issue_id=None, do=None):
        """ Close or reopen an issue """
        if issue_id:
            issue_uid = self.api.issue_iid_to_uid(issue_id)
            if not issue_uid:
                print(color('FAIL', "Issue {0} not found").format(issue_id))
                sys.exit(1)

            if do == 'close':
                state_event = 'close'
            elif do == 'reopen':
                state_event = 'reopen'
            else:
                raise ValueError('do must be close or reopen')

            ret_val = self.api.edit_issue(issue_uid, state_event=state_event)
            if ret_val['state'] == 'closed':
                print(color('GREEN', "Issue {0} closed").format(issue_id))
            elif ret_val['state'] == 'reopened':
                print(color('GREEN', "Issue {0} reopened").format(issue_id))
            else:
                print(color('FAIL', "Issue {0} has state: {1}").format(issue_id, ret_val['state']))
        else:
            print(color('WARNING', "Issue ID must be provided"))

    def write_patch_for_issue(self, issue_id=None):
        """ Workflow for resolving an issue, step 1:
            Open a branch """

        # first we have to do a few consistency checks
        try:
            issue_id = int(issue_id)
        except ValueError:
            print(color('WARNING', "ID must be an integer"))
            sys.exit(1)

        if not git.is_git_repo():
            print(color('WARNING', "Not a git repository"))
            sys.exit(1)

        p_id = self.api.get_project_id()

        # Transform iid to id
        issue_uid = self.api.issue_iid_to_uid(issue_id)

        issue = self.api.getprojectissue(p_id, issue_uid)
        if not issue:
            print(color('WARNING', "Issue ID not found"))
            sys.exit(1)

        if issue['project_id'] != p_id:
            print(color('WARNING', "The issue ID do not correspond to the current git repository/project"))
            sys.exit(1)

        # the workflow itself:
        # 1. create a branch
        # 2. switch to that branch.
        git.change_or_create_branch("issue_" + str(issue_id))

    def commit_patch(self, assignee_id=None, mr_text=None):
        """ Commit the patch and provide a mergerequest """

        if git.get_current_branch() == "master":
            print(color('WARNING', "You can not open a mergerequest from your local master branch.\nPlease switch to your issue branch!"))
            sys.exit(1)

        if not git.branch_is_clean():
            output = git.git(['status', '-s'])
            print(output)
            print(color('WARNING', "You have uncommitted changes. Please commit them first"))
            sys.exit(1)

        # We have to do some validating:
        # 1. Check whether the current commit is already in the remote master branch
        # 2. If not if we need to push our local changes to the remote. There might be 2 reasons:
        #   - The source_branch of the mergerequest doesn't exists on the remote.
        #   - The source_branch exists but we have new commits for that MR
        #
        #  We now have our local changes at the remote in a seperate branch.
        #  So wen move on:
        #
        #  3. If there is no MR present, create one.
        #
        #  Pray.

        # Step 1: Check whether the commit exist in the remote master branch
        last_local_sha = git.get_last_commit_sha()
        sha_is_on_remote = git.is_commit_on_remote(last_local_sha)

        if sha_is_on_remote:
            print(color('WARNING', "Your local commit is already in the remote master branch.\nAborting!"))
            sys.exit()

        # Step 2: Check whether we have to push our local changes to the remote

        need_push = False

        p_id = self.api.get_project_id()
        sourcebranch = git.get_current_branch()

        print("Branch: " + color('GREEN', sourcebranch))

        # First check whether the MR branch exists on the remote
        sourcebranch_on_remote = self.api.remote_branch_exists(sourcebranch, p_id)

        if not sourcebranch_on_remote:
            need_push = True
        else:
            # Second check whether we have un-pushed local commits.
            # We check the local source branch compared to the remote
            # source branch.
            unpushed_commits = git.need_pull_push(True, sourcebranch, sourcebranch)
            if unpushed_commits == 2:
                need_push = True

        if need_push:
            print(color('INFO', "Pushing to origin " + sourcebranch))
            git.git(['push', 'origin', sourcebranch])
        elif not need_push:
            print(color('INFO', "Local and remote are up-to-date."))
        else:
            print(color('WARNING', "Something went wrong."))
            sys.exit(1)

        # We are done with pushing commits.
        # Step 3. Creating a MR
        if assignee_id:
            try:
                assignee_id = int(assignee_id)
            except ValueError:
                print(color('WARNING', "ID must be an integer"))
                sys.exit(1)

        targetbranch = 'master'
        if mr_text:
            title = str(mr_text)
        else:
            title = git.git(['log', '--format=%s', '-n', '1'])
        is_new_mergerequest = self.api.is_mergerequest_new(sourcebranch, targetbranch)

        if is_new_mergerequest:
            print(color('GREEN', "Create a new mergerequest"))
            self.api.createmergerequest(p_id, sourcebranch, targetbranch, title, assignee_id=assignee_id)
        else:
            print(color('INFO', "Mergerequests exists. Skipping"))

    def list_project_members(self):
        """ Display a list of all projectmembers """
        members = self.api.list_group_members()
        if members:
            for member in members:
                print(color('INFO', "Name: " + member['name']))
                print(color('GREEN', "ID: " + str(member['id'])))

    def list_all_mergerequests(self, all=False):
        """ Display all open mergerequests of a project """
        mergerequests = self.api.get_all_mergerequests()
        for mergerequest in mergerequests:
            if not all and mergerequest['state'] == 'closed' or mergerequest['state'] == 'merged':
                continue

            print(color('INFO', "TITLE: " + mergerequest['title']))
            print(color('GREEN', "BRANCH: " + mergerequest['source_branch']))
            if mergerequest['assignee']:
                print(color('GREEN', "ASSIGNEE: " + mergerequest['assignee']['name']))
            print(color('GREEN', "ID: " + str(mergerequest['id'])))
            print(color('GREEN', "DATE: " + str(mergerequest['created_at'])))
            print("-") * 80

    def get_mergerequest_details(self, mergerequest_id=None):
        """ Display the details of a mergerequest """
        values = self.api.get_mergerequest_details(mergerequest_id)
        change = values['changes']
        comments = values['comments']

        if not change:
            print(color('FAIL', "Mergerequest not found"))
            sys.exit(1)

        print(color('INFO', "TITLE: " + change['title']))
        print(color('INFO', "AUTHOR: " + change['author']['name']))
        print(color('INFO', "STATE: " + change['state']))
        print(color('INFO', "DATE: " + change['created_at']))
        print(color('INFO', "DIFF:\n"))
        for chg in change['changes']:
            print(chg['diff'])

        print(color('INFO', "COMMENTS:"))
        for comment in comments:
            print(comment['author']['name'] + ":")
            print(comment['note'] + "\n" + "-" * 40)

    def accept_mergerequest(self, mergerequest_id=None):
        """ Accept a mergerequest """
        do_merge = query_yes_no("Should mergerequest " + mergerequest_id + " be merged?", "no")

        if do_merge:
            print(color('GREEN', "Start merge"))
            return_values = self.api.accept_mergerequest(mergerequest_id)

            if return_values and return_values['state'] == 'merged':
                print(color('GREEN', "Merge complete. Remove " + return_values['source_branch']))
                git.git(['push', 'origin', '--delete', return_values['source_branch']])
            else:
                print(color('FAIL', "Mergerequest already closed? Is there a mergerequest with this ID?"))
        else:
            print(color('INFO', "Merge aborted!"))