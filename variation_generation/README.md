# Variation Generator

## Description

This script will take an input TXT file and generate a CSV of multiple variations.


## Usage

Simply call the generate_variations function and pass it your input file name. Optional parameters allow you to name the output something different and to supress the printing of varaitions in the console.

```python
def generate_variation(input_file, output_file=None, verbose=True)
```
If no output_file is passed, the output_file will have the same name as the input_file, but with the .CSV extenstion, rather than the .TXT extension.


## Input file format
In your input file, simply enclose the sections you want to vary with double brackets [[ ]] and then put doubel pipes || between the variations themselves.

### Sample Input
```
This script will [[generate||create]] your [[versions||variations]].
```
### Sample Output
```
This script will generate your versions.
This script will generate your variations.
This script will create your versions.
This script will create your variations.
```