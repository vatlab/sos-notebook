import time
def test_magics(notebook):

	#test %pwd
    notebook.shift_kernel(index=0,kernel_name="Python3",by_click=True)
    command="%pwd"
    notebook.edit_cell(index=0,content=command,render=True)
    assert len(notebook.get_cell_output(index=0))>0

    #test %capture
    command="%capture --to R_out \n cat('this is to stdout')"
    notebook.add_and_execute_cell_in_kernel(index=0,content=command,kernel="R")
    assert 'this is to stdout'==notebook.get_cell_output(index=1)

    command="%capture --to R_out \n paste('this is the return value')"
    notebook.add_and_execute_cell_in_kernel(index=1,content=command,kernel="R")
    command="R_out"
    notebook.add_and_execute_cell_in_kernel(index=2,content=command,kernel="SoS")
    assert "''"==notebook.get_cell_output(index=3)

    command="%capture text --to R_out \n paste('this is the return value')"
    notebook.add_and_execute_cell_in_kernel(index=3,content=command,kernel="R")
    command="R_out"
    notebook.add_and_execute_cell_in_kernel(index=4,content=command,kernel="SoS")
    assert "this is the return value" in notebook.get_cell_output(index=4)


