import time
def test_shift_kernel(notebook):
	kernels=notebook.get_kernel_list()
	assert "SoS" in kernels
	assert "R" in kernels
	assert "Python 3" in kernels


	notebook.shift_kernel(index=0,kernel_name="R",by_click=True)
	command="%preview -n rn[1:3] \n rn <- rnorm(50)"
	notebook.edit_cell(index=0,content=command,render=True)

	assert "rn[1:3]" in notebook.get_cell_output(index=0)

    
	command="%get rn --from R \n len(rn)"
	notebook.append(command)
	notebook.shift_kernel(index=1,kernel_name="SoS")
	time.sleep(10)
	notebook.execute_cell(1)
	assert "50" in notebook.get_cell_output(index=1)

   



