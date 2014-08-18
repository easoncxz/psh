#!/usr/bin/env python3

import sys
import os
import signal
import traceback
import readline
from collections import OrderedDict
from copy import deepcopy

from line_to_words import word_list as parse

debugging = False

debug = print if debugging else lambda *x: None

class PSHUserError(Exception):
    pass

class PSHProgrammerError(Exception):
    pass

class JobList(OrderedDict):
    '''This class simply implements an abstract data type.
    All operations on a JobList object makes no effect on anything else, e.g. processes.
    '''

    def add(self, pid=None, command=None):
        '''Adds a pid and a command to the job list, returning the job of the process just added.'''
        if not pid or not command:
            raise PSHProgrammerError("To add a new job list entry, provide both the pid and the command of the job.")
        elif not self:
            jid = 1
        else:
            jid = max(self.keys()) + 1
        self[jid] = {
            'pid': pid,
            'command': command
        }
        return jid

    def get(self, jid=None):
        '''Returns a dictionary with keys "pid" and "command" that holds info about the job of the given jid.
        If not job with such jid exists, returns `None`.'''
        if not jid:
            raise PSHProgrammerError("To get a job's info, you need to supply a jid.")
        else:
            return self.get(jid)

    def delete(self, jid=None):
        '''If a job with the given jid currently exists, delete that job from the job list.'''
        if jid and pid:
            if self.get(jid) == pid:
                del self[jid]
            else:
                raise PSHProgrammerError("The jid-pid correspondence is wrong.")
        elif jid:
            if jid in self:
                del self[jid]
        elif pid:
            for jid in self:
                if self[jid] == pid:
                    del self[jid]

    def __sub__(self, other):
        '''Returns the jobs that are in this job list but not the other'''
        if not isinstance(other, JobList):
            raise TypeError("Cannot find difference between a JobList and a different thing.")
        else:
            return {k: self[k] for k in self if k not in other}

job_list = JobList()

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

def get_process_state(pid):
    '''Retrievs the current state of the given process, in a human-friendly form.
    If there is no such process, `None` will be returned.
    '''
    debug("Trying to get something about process of pid {}".format(pid))

    import subprocess
    if type(pid) is not int:
        raise PSHProgrammerError("pid should be an int.")
    ps_output_lines = subprocess.getoutput('ps -p {pid} -o state='.format(pid=pid)).splitlines()
    if not ps_output_lines:
        return None
    elif len(ps_output_lines) == 1:
        return state_description_for_code[ps_output_lines[0][0]]
    else:
        debug("The lines outputted were:")
        debug(ps_output_lines)
        raise PSHProgrammerError("WTH Multiple processes with the same pid??")

def make_job_description(jid, state, command):
    '''Formats the given information into a line of text suitable for displaying to the user.'''
    return "[{jid}] <{state}>\t\t{command}".format(
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
            for jid in job_list:
                print(make_job_description(
                    jid=jid, 
                    state=get_process_state(job_list[jid]['pid']),
                    command=job_list[jid]['command']))
            return True

def exec_one_command(command):
    '''Takes a non-empty list as the argument.
    Calling this function will cause the current program to be dumped out of the current process!'''
    # debug("exec_one_command running on command:", repr(command))

    try:
        if not command or not command[0]:
            raise PSHProgrammerError("Empty command passed to exec_one_command.")
        if command.count('&') > 1:
            raise PSHUserError("Sorry, the programmer didn't know what to do with multiple ampersands in one command.")
        command = [token for token in command if token != '&']  # get rid of the '&'s from the command - we've already consdiered it in `main`.

        if '|' in command:
            prev_commands, last_command = split_on_last_pipe(command)
            pipein, pipeout = os.pipe()  # create a pipe, and make a note of the file descriptors. `pipein` is analogous to `stdin`, and `pipeout` is analogous to `stdout`.
            pid = os.fork()  # fork!
            if not pid:  # child, which deals with all the stuff before the last pipe. It is the producer.
                def sigpipe_callback(sig, frame):
                    pass  # nothing
                signal.signal(signal.SIGPIPE, sigpipe_callback)
                producer_pid = os.fork()
                if not producer_pid:  # producer
                    os.dup2(pipeout, sys.stdout.fileno())  # Overwrite file of the descriptor 1 with file of descriptor `pipeout`, in the open file table. (1 for STDOUT.)
                    os.close(pipein)  # Since we've already plugged the reading end of the pipe in place, we can get rid of the initial entry of the pipe in the open file table.
                    os.close(pipeout)  # Same as the line above, we forget about the other end of the pipe as well.
                    exec_one_command(prev_commands)  # Recursive call that deals with the remaining pipes.
                else:  # proucer wrapper
                    try:
                        os.waitpid(producer_pid, 0)
                    except InterruptedError as ie:  # happens when SIGPIPE is caught.
                        os.kill(producer_pid, signal.SIGTERM)
                    finally:
                        suicide()
            else:  # parent, which runs the last command in the whole pipeline. It is the consumer.
                os.dup2(pipein, sys.stdin.fileno())  # In the open file table, connect the reading end of the pipe onto where STDIN used to be.
                os.close(pipein)  # Get rid of the (duplicate) handles onto the pipe in our open file table.
                os.close(pipeout)
                exec_one_command(last_command)  # Finally, execute the last command in the pipeline.
        elif run_builtin(command):  # `run_builtin` is one of my custom functions, which attempts to run the command as a builtin, and returns `True` is it did run.
            suicide()  # Imitate the `exec` behaviour of throwing our own process away. If this isn't done, there'll be multiple copies of this shell running in the user's terminal.
        else:  # An external command is needed.
            try:
                os.execvp(command[0], command)  # Run the external command using the PATH environment variable with which the user started this shell.
            except FileNotFoundError as e:
                raise PSHUserError("Bad command or file name.")
    except PSHUserError as e:
        print(e)
    except Exception as e:  # We must not allow any exceptions to be thrown back to the caller of this function, otherwise we'll end up having more processes running than we expect.
        traceback.print_exc()  # prints stack trace, which is what'll usually be done if an exception isn't caught.
    finally:
        suicide()  # Remember what the docstring says - a process that enters this function has to die!

def main():
    global init_dir
    global job_list
    init_dir = os.getcwd()
    if not os.isatty(sys.stdin.fileno()):
        prompt = ''
    else:
        prompt = 'psh> '
    previous_job_list = JobList()
    while True:
        try:
            # Get rid of zombies
            debug("job_list: ", job_list)
            for jid in job_list:
                state = get_process_state(job_list[jid]['pid'])
                if not state:  # process doesn't even exist anymore
                    del job_list[jid]
                elif state == 'Zombie':
                    os.waitpid(job_list[jid]['pid'], 0)  # Shouldn't take time at all
                    del job_list[jid]

            # Show "Done" jobs
            done_jobs = previous_job_list - job_list
            debug("done_jobs: ", done_jobs)
            for jid in done_jobs:
                print("[{}]  <Done>\t\t{}".format(jid, ' '.join(done_jobs[jid]['command'])))
            del done_jobs

            command = parse(input(prompt))
            if command:
                if '|' in command or not run_builtin(command):
                    # This means that if a builtin command is to take effect, it has to not be in any pipeline.
                    # If a builtin command is in a pipeline, it will end up in a different process.


                    top_pid = os.fork()
                    if top_pid == 0:  # So that we still have our shell after executing the command!
                        exec_one_command(command)
                    else:  # In the parent process
                        if command[-1] == '&':
                            # We were asked to run the command in background.
                            # Note that the command has *already started running*.
                            jid = job_list.add(pid=top_pid, command=command)
                        else:
                            # We were asked to run the command in foreground.
                            def sigtstp_callback(s, f):
                                pass
                            signal.signal(signal.SIGTSTP, sigtstp_callback)
                            try:
                                os.waitpid(top_pid, 0)
                            except InterruptedError as ie:  # happens upon catching SIGTSTP
                                jid = job_list.add(pid=top_pid, command=command)
                                print('[{}]   {}'.format(jid, top_pid))
                            finally:
                                del sigtstp_callback
                    del top_pid
            previous_job_list = deepcopy(job_list)
        except PSHUserError as e:
            print(e)
        except KeyboardInterrupt as e:
            print()
        except EOFError as e:
            print()
            return

if __name__ == '__main__':
    main()