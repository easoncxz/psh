#!/usr/bin/env python3

import sys
import os
import signal
import traceback
import readline
from collections import OrderedDict
from copy import deepcopy

from line_to_words import word_list as parse

debugging = True

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

previous_job_list = JobList()

previous_foreground_jid = None

previous_foreground_pid = None

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
    # debug("Trying to get something about process of pid {}".format(pid))

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


def add_raw_command_to_history(raw_command):
    global history_list
    if not history_list:
        history_list[1] = raw_command
    else:
        history_list[1 + max(history_list.keys())] = raw_command
        debug(dict(history_list))
    if len(history_list) > 10:
        del history_list[min(history_list.keys())]

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
        # debug("split result:", prev_commands, last_command)
        if not prev_commands or not last_command or prev_commands[0] == '|' or prev_commands[-1] == '|' or last_command[0] == '|' or last_command[-1] == '|':
            raise PSHUserError("Your pipe syntax is wrong. Please make sure there are commands on both sides of all your pipes.")
        else:
            return prev_commands, last_command

def wait_for_foreground(jid, pid):
    '''Assume the process of the given pid is nwo running in the foreground,
    we wait for it, and also listen to SIGTSTP.'''
    def sigtstp_callback(s, f):
        pass
    signal.signal(signal.SIGTSTP, sigtstp_callback)
    try:
        os.waitpid(pid, 0)
    except InterruptedError as ie:  # happens upon catching SIGTSTP
        os.kill(pid, signal.SIGSTOP)
        print('[{}]   {}'.format(jid, pid))
    except ChildProcessError as cpe:
        pass

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
        elif name == 'fg':
            # if job_list:
            #     jid = max(job_list)  # Get the most recent job
            #     pid = job_list[jid]['pid']
            #     os.kill(pid, signal.SIGCONT)
            #     debug('job_list:', job_list)
            if previous_foreground_pid:
                os.kill(previous_foreground_pid, signal.SIGCONT)
                wait_for_foreground(previous_foreground_jid, previous_foreground_pid)
        elif name == 'history' or name == 'h':
            global history_list
            if len(command) <= 1:
                for i in history_list:
                    print(i,':\t', history_list[i])
                return True
            else:
                hid = None
                try:
                    hid = int(command[1])
                except ValueError as ve:
                    raise PSHUserError("History number isn't an integer.")
                if hid in history_list:
                    raw_command = history_list[hid]
                    command = parse(raw_command)

                    # Rewrite history!
                    history_list[max(history_list.keys())] = raw_command

                    run_one_command(command)
                    return True
                else:
                    raise PSHUserError("No such history number.")
        elif debugging and name == 'debug':
            import code
            code.interact(local=globals())

def exec_one_command(command):
    '''Takes a non-empty list as the argument.
    Calling this function will cause the current program to be dumped out of the current process!'''

    try:
        if not command or not command[0]:
            raise PSHProgrammerError("Empty command passed to exec_one_command.")
        if command.count('&') > 1:
            raise PSHUserError("Sorry, the programmer didn't know what to do with multiple ampersands in one command.")
        command = [token for token in command if token != '&']  # get rid of the '&'s from the command - we've already consdiered it in `main`.

        if '|' in command:
            # Split the one command into two commands.
            # The second command will be the consumer, who consumes the output produced
            # by the "previous commands", which is the producer.
            prev_commands, last_command = split_on_last_pipe(command)

            # Create a pipe, and make a note of the file descriptors.
            # `pipein` is analogous to `stdin`, which will be read from by the consumer.
            # `pipeout` is analogous to `stdout`. which will be wrote to, by the producer.
            pipein, pipeout = os.pipe()  

            # Notice that we created a pipe *before* we forked.
            # That way, the two processes will have access to *the same* pipe.
            pid = os.fork()
            if not pid:  # This is the child, which is all the "previous commands". It is the producer.
                # If the consumer dies before this producer finishes producing output,
                # we would get a "broken pipe" problem. To solve this,
                # we "wrap" the producer around another process which listens
                # to, and handles, the SIGPIPE signal sent by the OS when the (or all)
                # process at the other end of the pipe we're holding have terminated.

                def sigpipe_callback(sig, frame):
                    pass  # just defining a function.
                signal.signal(signal.SIGPIPE, sigpipe_callback)  # registering a listener
                producer_pid = os.fork()  # Create the "wrapping" process
                if not producer_pid:  # the actual producer
                    # Plug the writable end of the pipe into where stdout used to be.
                    # This is done by overwriting the stdout file descriptor with the 
                    # writable end of the pipe.
                    os.dup2(pipeout, sys.stdout.fileno())

                    # We don't need more file descriptors pointing to the pipe,
                    # and it's a better idea to start the command in a clean state.
                    os.close(pipein)
                    os.close(pipeout)

                    # Recursive call that deals with the remaining pipes.
                    exec_one_command(prev_commands) # Being an `exec`, this function call doesn't return.
                else:  # the proucer wrapper
                    try:
                        os.waitpid(producer_pid, 0)
                    except InterruptedError as ie:
                        # This happens when SIGPIPE is caught.
                        # It means that the consumer has gone.
                        # We'll tell the producer to terminate too.
                        os.kill(producer_pid, signal.SIGTERM)
            else:  # This is the parent, which is last command of the pipeline. It is the consumer.
                # Plug the readable end of the pipe into the stdin port of our process
                os.dup2(pipein, sys.stdin.fileno())

                # Let go of the extra handles onto the pipe
                os.close(pipein)
                os.close(pipeout)

                # Finally, execute the last command in the pipeline.
                exec_one_command(last_command)
                # As before, this `exec` call doesn't return.
        elif not run_builtin(command):
            # `run_builtin` is one of my custom functions, which attempts to run the
            # command as a builtin, and returns `True` if it did indeed run successfully.

            # If control reaches here, it means that the command to be executed is not a builtin.
            # Hence we treat it as an external.
            try:
                # Run the external command using the PATH environment variable with which the user started this shell.
                os.execvp(command[0], command)
            except FileNotFoundError as e:  # Obviously, the "external command" might just be gibberish.
                raise PSHUserError("Bad command or file name.")
    except PSHUserError as e:
        print(e)
    except Exception as e:  # We must not allow any exceptions to be thrown back to the caller of this function, otherwise we'll end up having more processes running than we expect.
        traceback.print_exc()  # prints stack trace, which is what'll usually be done if an exception isn't caught.
    finally:
        # To complete the recursive process, this exit of the 
        # function also needs to "dump the entire process away" and
        # "not return" too, as its docstring says.
        suicide()


def run_one_command(command):
    '''Run the given command, and wait for it.
    The process calling this function won't be exec'ed.'''
    top_pid = os.fork()
    if top_pid == 0:
        # child
        # we'll use this process to run the actual command.
        exec_one_command(command)
    else:
        # parent
        # we'll use this process to do the blocking waiting,
        # and the signal handling.
        if command[-1] == '&':
            # We were asked to run the command in background.
            # Note that the command has *already started running*.
            # We simply don't wait for it.
            job_list.add(pid=top_pid, command=command)
            previous_job_is_backgrounded = True
        else:
            # We were asked to run the command in foreground.
            # Not only do we need to wait for it,
            # we also have to handle ^Z keypresses (i.e. SIGTSTP signals)
            
            previous_job_is_backgrounded = False
            previous_foreground_pid = top_pid
            previous_foreground_jid = jid
            wait_for_foreground(jid, top_pid)

def main():
    global init_dir
    global job_list
    global previous_job_list
    global previous_foreground_pid
    global previous_foreground_jid
    previous_job_is_backgrounded = None
    global history_list
    init_dir = os.getcwd()
    if not os.isatty(sys.stdin.fileno()):
        prompt = ''
    else:
        prompt = 'psh> '
    while True:
        try:
            # Get rid of zombies
            # debug("job_list: ", job_list)
            for jid in job_list:
                state = get_process_state(job_list[jid]['pid'])
                if not state:  # process doesn't even exist anymore
                    del job_list[jid]
                elif state == 'Zombie':
                    os.waitpid(job_list[jid]['pid'], 0)  # Shouldn't take time at all
                    del job_list[jid]

            # Show "Done" jobs
            done_jobs = previous_job_list - job_list
            # debug("done_jobs: ", done_jobs)
            if previous_job_is_backgrounded:
                for jid in done_jobs:
                    print("[{}]  <Done>\t\t{}".format(jid, ' '.join(done_jobs[jid]['command'])))
            del done_jobs

            # Get the command
            raw_command = input(prompt)
            command = parse(raw_command)
            add_raw_command_to_history(raw_command)

            # Run comand
            if command:
                if '|' in command or not run_builtin(command):
                    # This means that if a builtin command is to take effect, it has to not be in any pipeline.
                    # If a builtin command is in a pipeline, it will end up in a different process.
                    run_one_command(command)

            previous_job_list = deepcopy(job_list)
        except PSHUserError as e:
            print(e)
        except KeyboardInterrupt as e:  # catches ^C key presses
            print()  # cleans line, being about to read a new command.
        except EOFError as e:  # catches ^D key presses
            print()
            return  # terminates the shell

if __name__ == '__main__':
    main()