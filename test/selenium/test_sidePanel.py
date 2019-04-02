import time
def test_sidepanel(notebook):
	time.sleep(2)
	assert True==notebook.get_sidePanel()
	notebook.toggle_sidePanel()
	time.sleep(2)
	assert False==notebook.get_sidePanel()
	notebook.toggle_sidePanel()

	command="print(1)"
	notebook.edit_cell(index=0,content=command,render=False)
	notebook.execute_cell(cell_or_index=0,inPanel=True)
	time.sleep(2)
	# assert "1"==notebook.get_cell_output(index=1,inPanel=True)

	notebook.shift_kernel_inPanel(kernel_name="Python3", by_click=True)
	content="print(2)"
	notebook.edit_panel_input(content=content)

	
