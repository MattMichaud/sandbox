from itertools import product
import pandas as pd

def find_all(string, sub):
    start = 0
    while True:
        start = string.find(sub, start)
        if start == -1: return
        yield start
        start += len(sub)

def parse_input(filename):
    with open(filename, 'r') as f:
        data = f.read()
    print(data,'\n')
    openers = list(find_all(data, '[['))
    closers = list(find_all(data, ']]'))
    if len(openers) != len(closers):
        print('Open close mismatch')
        return(None)
    if len(openers) == 0:
        return(data)
    else:
        breakpoints = []
        for i in range(len(openers)):
            breakpoints.append(openers[i])
            breakpoints.append(closers[i])
        breakpoints.append(len(data))
        start = 0
        result_list = []
        for b in breakpoints:
            sub = data[start:b]
            start += len(sub)
            sub = sub.replace('[[','').replace(']]','')
            if '||' in sub:
                sub = sub.split('||')
            else:
                sub = [sub]
            result_list.append(sub)
        return(result_list)

def print_line(length = 100, symbol = '-'):
    print(symbol * length)

def print_results(df, field):
    print('Total Versions:', len(df),'\n')
    for index, row in df.iterrows():
        print_line()
        print('Version:',index)
        print_line()
        print(row[field])

def generate_variations(input_file, verbose=True, output_file=None):
    import os
    abspath = os.path.abspath(__file__)
    dname = os.path.dirname(abspath)
    os.chdir(dname)

    if not output_file:
        output_file = input_file.replace('.txt','.csv')

    df = pd.DataFrame([''.join(element) for element in product(*parse_input(input_file))], columns=['text'])
    df.to_csv(output_file, header=False, index=False)
    if verbose:
        print_results(df, 'text')




generate_variations(input_file='test_input.txt', output_file='output2.csv', verbose=True)