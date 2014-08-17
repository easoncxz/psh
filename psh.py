#!/usr/bin/env python3

import sys
import os
import signal
import traceback

from line_to_words import word_list

parse = word_list

class PSHUserError(Exception):
    pass

class PSHProgrammerError(Exception):
    pass

class JobList:

    def __init__(self):
        self._dict = dict()

    def add(self, pid, command):
        if not self._dict:
            jid = 1
        else:
            jid = max(self._dict.keys()) + 1
        self._dict[jid] = (pid, command)
        return jid

    def get(self, jid):
        return self._dict.get(jid)

    def delete(self, jid=None, pid=None):
        if jid and pid:
            if self._dict.get(jid) == pid:
                del self._dict[jid]
            else:
                raise PSHProgrammerError("The jid-pid correspondence is wrong.")
        elif jid:
            if jid in self._dict:
                del self._dict[jid]
        elif pid:
            for jid in self._dict:
                if self._dict[jid] == pid:
                    del self._dict[jid]

    def as_table(self):
        return [(jid, self._dict[jid][0], self._dict[jid][1]) for jid in sorted(self._dict)]

job_list = JobList()

debugging = False

debug = print if debugging else lambda *x: None

init_dir = None

def suicide():
    os.kill(os.getpid(), signal.SIGTERM)

state_description_for_code = {
    'I': 'Idle',
    'R': 'Runnable',
    'S': 'Sleeping',
    'T': 'Stopped',
    'U': 'Uninterruptable',
    'Z': 'Zombie',
}

def get_process_something(pid, *things):
    import subprocess
    ps_output_lines = subprocess.getoutput('ps -p {pid} -o {things}='.format(
            pid=pid,
            things=','.join(things)
        )).splitlines()
    if not ps_output_lines:
        raise PSHProgrammerError("Attempted to get info of a non-existant process.")
    elif len(ps_output_lines) == 1:
        return ps_output_lines[0]
    else:
        raise PSHProgrammerError("WTH Multiple processes with the same pid??")

def get_process_state(pid):
    code = get_process_something(pid, 'state')[0]  # Read the first character of the line
    return state_description_for_code[code]

def get_process_command_head(pid):
    raw_command = get_process_something(pid, 'comm')
    return parse(raw_command)

def make_job_description(jid, state, command):
    return "[{jid}] {state}\t\t{command}".format(
            jid=jid,
            state=state,
            command=(' '.join(command)))

def split_on_last_pipe(command):
    '''Only takes a non-empty command that has at least one pipe as the argument.'''
    if not command:
        raise PSHProgrammerError("You tried to split an empty command on its (non-existant) last pipe.")
    elif '|' not in command:
        raise PSHProgrammerError("Stupid programmer! The split_on_last_pipe function only takes commands that *have* a pipe.")
    else:
        ind = len(command) - 1  # we start by looking at the last token of the command
        while ind >= 0:
            if command[ind] == '|':
                break
            else:
                ind -= 1
        prev_commands, last_command = command[:ind], command[ind + 1:]
        debug("split result:", prev_commands, last_command)
        if not prev_commands or not last_command or prev_commands[0] == '|' or prev_commands[-1] == '|' or last_command[0] == '|' or last_command[-1] == '|':
            raise PSHUserError("Your pipe syntax is wrong. Please make sure there are commands on both sides of all your pipes.")
        else:
            return prev_commands, last_command

def run_builtin(command):
    '''Takes a non-empty list as the argument.
    Calling this function will cause the current program to be dumped out of the current process!
    Returns `True` upon successful finish.'''

    if not command:
        raise PSHProgrammerError("An empty command has been treated as a builtin.")
    else:
        name = command[0]
        if name == 'cd':
            if len(command) == 1:  # The command was `cd`, with no argument.
                os.chdir(init_dir)
                return True
            else:  # There was some arguments.
                try:
                    os.chdir(command[1])  # Ignores the command line args after the first arg, like how Bash does.
                    return True
                except FileNotFoundError as e:
                    raise PSHUserError("Folder does not exist.")
                finally:
                    pass
        elif name == 'pwd':
            print(os.getcwd())
            return True
        elif name == 'jobs':
            jobs_table = job_list.as_table()
            for jid, pid, command in jobs_table:
                print(make_job_description(jid=jid, state=get_process_state(pid), command=command))
            return True

def exec_one_command(command):
    '''Takes a non-empty list as the argument.
    Calling this function will cause the current program to be dumped out of the current process!'''
    debug("exec_one_command running on command:", repr(command))

    try:
        if not command or not command[0]:
            raise PSHProgrammerError("Empty command passed to exec_one_command.")
        if command.count('&') > 1:
            raise PSHUserError("Sorry, the programmer didn't know what to do with multiple ampersands in one command.")
        command = [token for token in command if token != '&']

        if '|' in command:
            prev_commands, last_command = split_on_last_pipe(command)
            pipein, pipeout = os.pipe()
            pid = os.fork()
            if not pid:  # child, which deals with all the stuff before the last pipe
                os.dup2(pipeout, 1)  # 1 for STDOUT
                os.close(pipein)
                os.close(pipeout)
                exec_one_command(prev_commands)  # require checking!!
            else:  # parent
                os.waitpid(pid, 0)
                os.dup2(pipein, 0)  # 0 for STDIN
                os.close(pipein)
                os.close(pipeout)
                exec_one_command(last_command)  # require checking!!
        elif run_builtin(command):
            suicide()  # Imitate the `exec` behaviour of throwing our own process away.
        else:
            try:
                os.execvp(command[0], command)
            except FileNotFoundError as e:
                raise PSHUserError("Bad command or file name.")
    except PSHUserError as e:
        print(e)
        suicide()
    except Exception as e:
        traceback.print_exc()
        suicide()

def main():
    global init_dir
    global job_list
    init_dir = os.getcwd()
    if not os.isatty(sys.stdin.fileno()):
        prompt = ''
    else:
        prompt = 'psh> '
    while True:
        try:
            jobs_table_before = [(jid, pid, command, get_process_state(pid)) for (jid, pid, command) in job_list.as_table()]
            command = parse(input(prompt))
            if command:
                if '|' in command or not run_builtin(command):
                    # This means that if a builtin command is to take effect, it has to not be in any pipeline.
                    # If a builtin command is in a pipeline, it will end up in a different process.

                    top_pid = os.fork()
                    if top_pid == 0:  # So that we still have our shell after executing the command!
                        exec_one_command(command)
                    elif command[-1] == '&':  # (If) We were asked to run the command in background
                        # Note that the command has *already started running*.
                        jid = job_list.add(top_pid, command)
                        state = get_process_state(pid=top_pid)
                        print(make_job_description(jid=jid, state=state, command=command))
                    else:
                        os.waitpid(top_pid, 0)

            # Show state changes of previously-run commands
            for jid, pid, command, state_before in jobs_table_before:
                state_now = get_process_state(pid)
                if state_now != state_before:
                    print(make_job_description(jid, state_now, command))

        except PSHUserError as e:
            print(e)
        except EOFError as e:
            print()
            return

if __name__ == '__main__':
    main()