
import os
import signal

from line_to_words import word_list as parse

class CtrlZHappenedError(Exception):
    pass

def sigtstp_callback(sig, frame):
    # input('Now vim again.')
    pass

def one():
    signal.signal(signal.SIGTSTP, sigtstp_callback)
    pid = os.fork()
    if not pid:
        os.execvp('./infinite.py', ['./infinite.py'])
    else:
        while True:
            try:
                os.waitpid(pid, 0)
            except InterruptedError as ie:
                input("sorry, ctrl-z is disabled.")
                os.kill(pid, signal.SIGCONT)
                continue
            break

def two():
    signal.signal(signal.SIGTSTP, sigtstp_callback)
    pid = os.fork()
    if not pid:
        os.execvp('vim', ['vim'])
    else:
        try:
            os.wait()
        except InterruptedError as ie:
            input("Vim will be sent SIGTERM now.")
            os.kill(pid, signal.SIGTERM)
            # os.waitpid(pid, 0)

pid = None
child_pid = None

def three():
    signal.signal(signal.SIGTSTP, sigtstp_callback)
    global pid
    global child_pid
    while True:
        command = parse(input())
        if command[0] == 'fg':
            print('child_pid again:', child_pid)
            os.kill(child_pid, signal.SIGCONT)
            os.waitpid(child_pid, 0)
        else:
            pid = os.fork()
            if not pid:
                child_pid = os.getpid()
                print('child_pid:', child_pid)
                os.execvp(command[0], command)
            else:
                try:
                    os.waitpid(pid, 0)
                except InterruptedError as ie:
                    continue

if __name__ == '__main__':
    three()