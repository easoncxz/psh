#!/usr/bin/env python3

import sys, os

from line_to_words import word_list

class PSHUserError(Exception):
    pass

class PSHProgrammerError(Exception):
    pass

debugging = False

debug = print if debugging else lambda *x: None

parse = word_list

builtins = {
    'cd'
}

def split_on_last_pipe(command):
    '''Only takes a command that has at least one pipe as the argument.'''
    if '|' not in command:
        raise PSHProgrammerError("Stupid programmer! The split_on_last_pipe function only takes commands that *have* a pipe.")
    ind = -1  # we start by looking at the last token of the command
    while command[ind] != '|':
        ind -= 1
    return command[:ind], command[ind + 1:]

def exec_one_command(command):
    '''Takes a non-empty list as the argument.
    Calling this function will cause the current program to be dumped out of the current process!'''

    if command.count('&') > 1:
        raise PSHUserError("Sorry, the programmer didn't know what to do with multiple ampersands in one command.")
    command = [token for token in command if token != '&']

    if '|' in command:
        pipein, pipeout = os.pipe()
        prev_command, last_command = split_on_last_pipe(command)
        pid = os.fork()
        if not pid:  # child, which deals with all the stuff before the last pipe
            os.dup2(pipeout, 1)  # 1 for STDOUT
            os.close(pipein)
            os.close(pipeout)
            exec_one_command(prev_command)  # require checking!!
        else:  # parent
            os.waitpid(pid, 0)
            os.dup2(pipein, 0)  # 0 for STDIN
            os.close(pipein)
            os.close(pipeout)
            exec_one_command(last_command)  # require checking!!
    else:
        os.execvp(command[0], command)

def main():
    while True:
        try:
            command = parse(input('psh> '))
            debug('the command was: ', command)
            if command:
                if command[0] in builtins:
                    print('Builtin {} is not implemented yet.'.format(command[0]))
                else:
                    top_pid = os.fork()
                    if top_pid == 0:  # So that we still have our shell after executing the command!
                        exec_one_command(command)
                    if command[-1] != '&':
                        os.waitpid(top_pid, 0)
        except PSHUserError as e:
            print(e)
        except EOFError as e:
            print()
            return

if __name__ == '__main__':
    main()