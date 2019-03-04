import time
def test_shift_kernel(notebook):
	kernels=notebook.get_kernel_list()
	assert "SoS" in kernels
	assert "R" in kernels
	backgroundColor={"SoS":[0,0,0],"R":[220,220,218],"python3":[255,217,26]}

    #test shift to R kernel by click
	notebook.shift_kernel(index=0,kernel_name="R",by_click=True)
	#check background color for R kernel
	assert all([a==b] for a,b in zip(backgroundColor["R"],notebook.get_input_backgroundColor(0)))
	
	command="%preview -n rn[1:3] \n rn <- rnorm(50)"
	notebook.edit_cell(index=0,content=command,render=True)

	assert "rn[1:3]" in notebook.get_cell_output(index=0)
	assert all([a==b] for a,b in zip(backgroundColor["R"],notebook.get_output_backgroundColor(0)))

    #test $get and shift to SoS kernel
	command="%get rn --from R \n len(rn)"
	notebook.append(command)
	notebook.shift_kernel(index=1,kernel_name="SoS")
	assert all([a==b] for a,b in zip(backgroundColor["SoS"],notebook.get_input_backgroundColor(1)))
	notebook.execute_cell(1)
	# assert "50" in notebook.get_cell_output(index=1)
	#check background color for SoS kernel
	assert all([a==b] for a,b in zip(backgroundColor["SoS"],notebook.get_output_backgroundColor(1)))

	
	command="%use python3"
	notebook.append(command)
	notebook.execute_cell(cell_or_index=2)
	assert all([a==b] for a,b in zip(backgroundColor["python3"],notebook.get_input_backgroundColor(2)))
	notebook.append("")
	assert all([a==b] for a,b in zip(backgroundColor["python3"],notebook.get_input_backgroundColor(3)))
	







    



