import time
def test_sosrun(notebook):
    command="[global]\nparameter: gvar = 20"
    notebook.shift_kernel(index=0,kernel_name="SoS",by_click=True)
    notebook.edit_cell(index=0,content=command,render=True)

    command="[workflow_10]\nprint('This is step {}, with {}'.format(step_name,gvar))"
    notebook.add_and_execute_cell_in_kernel(index=0,content=command,kernel="SoS")
    command="[workflow_20]\nprint('This is step {}, with {}'.format(step_name,gvar))"
    notebook.add_and_execute_cell_in_kernel(index=1,content=command,kernel="SoS")

    command="%sosrun workflow --gvar 40"
    notebook.add_and_execute_cell_in_kernel(index=2,content=command,kernel="SoS")
    output=notebook.wait_for_output(index=3)
    lines=output.splitlines()
    assert lines[0]=="This is step workflow_10, with 40"
    assert lines[1]=="This is step workflow_20, with 40"

    command='''[worker]
parameter: val=5
sh: expand=True
echo process {val}'''
    notebook.add_and_execute_cell_in_kernel(index=3,content=command,kernel="SoS")

    command='''%sosrun batch
[batch]
input: for_each={'val': range(2)}
sos_run('worker',val=val)'''
    notebook.add_and_execute_cell_in_kernel(index=4,content=command,kernel="SoS")
    output=notebook.get_cell_output(index=5)
    lines=output.splitlines()
    assert lines[0]=="process 0"

    command="%sossave check_sossave -f"
    notebook.add_and_execute_cell_in_kernel(index=5,content=command,kernel="SoS")

    command="%runfile check_sossave worker"
    notebook.add_and_execute_cell_in_kernel(index=6,content=command,kernel="SoS")
    output=notebook.wait_for_output(index=7)
    assert output=="process 5"



    

    