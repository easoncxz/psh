# Non class version
# This can be used to break a line into words suitable for this assignment.

import shlex

def word_list(line):
    """Break the line into shell words.
    """
    lexer = shlex.shlex(line, posix=True)
    lexer.whitespace_split = False
    lexer.wordchars += '#$+-,./?@^='
    args = list(lexer)
    return args

while True:
    line = input('psh> ')
    print(word_list(line))


    
