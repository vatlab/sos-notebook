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

    #test %expand
    command="par=100"
    notebook.add_and_execute_cell_in_kernel(index=5,content=command,kernel="SoS")
    command="%expand ${ } \n if (${par} > 50) { \n cat('A parameter ${par} greater than 50 is specified.');\n}"
    notebook.add_and_execute_cell_in_kernel(index=6,content=command,kernel="R")
    assert "A parameter 100 greater than 50 is specified."==notebook.get_cell_output(index=7)

    #test %get
    command="a = [1, 2, 3] \nb = [1, 2, '3']"
    notebook.add_and_execute_cell_in_kernel(index=7,content=command,kernel="SoS")
    command="%get a \n a"
    notebook.add_and_execute_cell_in_kernel(index=8,content=command,kernel="Python3")
    assert "[1, 2, 3]"==notebook.get_cell_output(index=9)
    command="%get b \nstr(b)\nR_var <- 'R variable'"
    notebook.add_and_execute_cell_in_kernel(index=9,content=command,kernel="R")
    assert "List of 3" in notebook.get_cell_output(index=10)
    command="%get --from R R_var \n R_var"
    notebook.add_and_execute_cell_in_kernel(index=10,content=command,kernel="Python3")
    assert "R variable" in notebook.get_cell_output(index=11)

    #test %put
    command="a = c(1)\n.b = c(1, 2, 3)\nc = matrix(c(1,2,3,4), ncol=2)\nR_var <- 'R variable'"
    notebook.add_and_execute_cell_in_kernel(index=11,content=command,kernel="R")
    command="%put a .b c"
    notebook.add_and_execute_cell_in_kernel(index=12,content=command,kernel="R")
    command="%preview -n a _b c"
    notebook.add_and_execute_cell_in_kernel(index=13,content=command,kernel="SoS")
    outputLines=notebook.get_cell_output(index=14).split("\n")
    assert "> a: int" == outputLines[0]
    assert "> _b: list of length 3" == outputLines[2]
    assert "> c: ndarray of shape (2, 2)" == outputLines[4]
    command="%put --to Python3 R_var"
    notebook.add_and_execute_cell_in_kernel(index=14,content=command,kernel="R")
    command="R_var"
    notebook.add_and_execute_cell_in_kernel(index=15,content=command,kernel="Python3")
    assert "'R variable'"==notebook.get_cell_output(index=16)



    














