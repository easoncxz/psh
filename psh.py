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

debugging = True

debug = print if debugging else lambda *x: None

builtins = {
    'cd',
    'pwd',

}

init_dir = None

def suicide():
    os.kill(os.getpid(), signal.SIGTERM)

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
    Calling this function will cause the current program to be dumped out of the current process!'''
    if not command:
        raise PSHProgrammerError("An empty command has been treated as a builtin.")
    else:
        name = command[0]
        if name not in builtins:
            raise PSHProgrammerError("A non-builtin command has been treated as a builtin.")
        elif name == 'cd':
            if len(command) == 1:  # The command was `cd`, with no argument.
                os.chdir(init_dir)
            else:  # There was some arguments.
                try:
                    os.chdir(command[1])  # Ignores the command line args after the first arg, like how Bash does.
                finally:
                    pass
        elif name == 'pwd':
            print(os.getcwd())

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
            debug("split result:", prev_commands, last_command)
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
        elif command[0] in builtins:
            run_builtin(command)
            suicide()  # Imitate the `exec` behaviour of throwing our own process away.
        else:
            try:
                os.execvp(command[0], command)
            except FileNotFoundError as e:
                raise PSHUserError("Bad command or file name.")
            finally:
                pass
    except PSHUserError as e:
        print(e)
        suicide()
    except Exception as e:
        traceback.print_exc()
        suicide()

def main():
    global init_dir
    init_dir = os.getcwd()
    while True:
        try:
            command = parse(input('psh> '))
            if command:
                if '|' not in command and command[0] in builtins:
                    # This means that if a builtin command is to take effect, it has to not be in any pipeline.
                    # If a builtin command is in a pipeline, it will end up in a different process.
                    run_builtin(command)
                else:
                    top_pid = os.fork()
                    if top_pid == 0:  # So that we still have our shell after executing the command!
                        exec_one_command(command)
                    elif command[-1] != '&':  # (If) We weren't asked to run the command in background
                        os.waitpid(top_pid, 0)
        except PSHUserError as e:
            print(e)
        except EOFError as e:
            print()
            return

if __name__ == '__main__':
    main()