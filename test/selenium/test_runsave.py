import time
def test_run(notebook):
	#test passing parameters and %run
    command='''%run --floatvar 1 --test_mode --INT_LIST 1 2 3 --infile a.txt
VAR = 'This var is defined without global.'
[global]
GLOBAL_VAR='This var is defined with global.'
[step_1]
CELL_VAR='This var is defined in Cell.'
parameter: floatvar=float
parameter: stringvar='stringvar'
print(VAR)
print(GLOBAL_VAR)
print(CELL_VAR)
print(floatvar)
print(stringvar)
[step_2]
parameter: test_mode=bool
parameter: INT_LIST=[]
parameter: infile = path
parameter: b=1
print(test_mode)
print(INT_LIST)
print(infile.name)
sh: expand=True
echo {b}
'''
    notebook.shift_kernel(index=0,kernel_name="SoS",by_click=True)
    notebook.edit_cell(index=0,content=command,render=True)
    output=notebook.get_cell_output(index=0)
    lines=output.splitlines()
    results=["This var is defined without global.","This var is defined with global.","This var is defined in Cell.","1.0","stringvar",
    		"True","['1', '2', '3']","a.txt","1"]
    for index, line in enumerate(lines):
    	assert lines[index]==results[index]

#test %save
    command='''%run --var 1
parameter: var=0
sh: expand=True
echo {var}
'''
    notebook.add_and_execute_cell_in_kernel(index=0,content=command,kernel="SoS")
    output=notebook.get_cell_output(index=1)
    lines=output.splitlines()
    assert lines[0]=="1"
    
    command='''%save check_run -f
%run --var 1
parameter: var=0
sh: expand=True
echo {var}
'''
    notebook.add_and_execute_cell_in_kernel(index=1,content=command,kernel="SoS")
    command="%runfile check_run --var=2"
    notebook.add_and_execute_cell_in_kernel(index=2,content=command,kernel="SoS")

   
    output=notebook.get_cell_output(index=3)
    assert output=="2"


   

    