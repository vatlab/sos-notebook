/**
 * Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
 * Distributed under the terms of the 3-clause BSD License.
 **/
define([
  "jquery",
  "codemirror/lib/codemirror",
  "codemirror/mode/python/python",
  "codemirror/mode/r/r",
  "codemirror/mode/octave/octave",
  "codemirror/mode/ruby/ruby",
  "codemirror/mode/sas/sas",
  "codemirror/mode/javascript/javascript",
  "codemirror/mode/shell/shell",
  "codemirror/mode/julia/julia",
  "codemirror/mode/markdown/markdown",
  "codemirror/addon/selection/active-line",
  "codemirror/addon/fold/foldcode",
  "codemirror/addon/fold/foldgutter",
  "codemirror/addon/fold/indent-fold"
], function($) {

  "use strict";
  //variables defined as global which enable access from imported scripts.
  window.BackgroundColor = {};
  window.DisplayName = {};
  window.KernelName = {};
  window.LanguageName = {};
  window.KernelList = [];
  window.KernelOptions = {};
  window.events = require("base/js/events");
  window.Jupyter = require("base/js/namespace");
  window.CodeCell = require("notebook/js/codecell").CodeCell;

  window.my_panel = null;
  window.pending_cells = {};

  window.sos_comm = null;

  var nb = IPython.notebook;

  // initialize BackgroundColor etc from cell meta data
  if (!("sos" in nb.metadata)) {
    nb.metadata["sos"] = {
      "kernels": [
        // displayed name, kernel name, language, color
        ["SoS", "sos", "", ""]
      ],
      // panel displayed, position (float or side), old panel height
      "panel": {
        "displayed": true,
        "style": "side",
        "height": 0
      },
    };
  } else if (!nb.metadata["sos"].panel) {
    nb.metadata["sos"].panel = {
      "displayed": true,
      "style": "side",
      "height": 0
    };
  }
  // Initial style is always side but the style is saved and we can honor this
  // configuration later on.
  nb.metadata["sos"]["panel"].style = "side";
  if (!nb.metadata["sos"].default_kernel) {
    nb.metadata["sos"]["default_kernel"] = "SoS";
  }

  var data = nb.metadata["sos"]["kernels"];
  // upgrade existing meta data if it uses the old 3 item format
  if (nb.metadata["sos"]["kernels"].length > 0 &&
    nb.metadata["sos"]["kernels"][0].length === 3) {
    for (var j = 0; j < nb.metadata["sos"]["kernels"].length; j++) {
      var def = nb.metadata["sos"]["kernels"][j];
      // original format, kernel, name, color
      // new format, name, kenel, lan, color
      nb.metadata["sos"]["kernels"][j] = [def[1], def[0], def[1], def[2]];
    }
    data = nb.metadata["sos"]["kernels"];
  }

  for (var i = 0; i < data.length; i++) {
    // BackgroundColor is color
    window.BackgroundColor[data[i][0]] = data[i][3];
    window.BackgroundColor[data[i][1]] = data[i][3];
    // DisplayName
    window.DisplayName[data[i][0]] = data[i][0];
    window.DisplayName[data[i][1]] = data[i][0];
    // Name
    window.KernelName[data[i][0]] = data[i][1];
    window.KernelName[data[i][1]] = data[i][1];
    // LanguageName
    window.LanguageName[data[i][0]] = data[i][2];
    window.LanguageName[data[i][1]] = data[i][2];
    // KernelList, use displayed name
    window.KernelList.push([data[i][0], data[i][0]]);
  }

  // if not defined sos version, remove extra kernels saved by
  // sos-notebook 0.9.12.7 or earlier
  if (!nb.metadata["sos"]["version"]) {
    save_kernel_info();
  }
  window.filterDataFrame = function(id) {
    var input = document.getElementById("search_" + id);
    var filter = input.value.toUpperCase();
    var table = document.getElementById("dataframe_" + id);
    var tr = table.getElementsByTagName("tr");

    // Loop through all table rows, and hide those who do not match the search query
    for (var i = 1; i < tr.length; i++) {
      for (var j = 0; j < tr[i].cells.length; ++j) {
        var matched = false;
        if (tr[i].cells[j].innerHTML.toUpperCase().indexOf(filter) !== -1) {
          tr[i].style.display = "";
          matched = true;
          break;
        }
        if (!matched) {
          tr[i].style.display = "none";
        }
      }
    }
  };

  window.sortDataFrame = function(id, n, dtype) {
    var table = document.getElementById("dataframe_" + id);

    var tb = table.tBodies[0]; // use `<tbody>` to ignore `<thead>` and `<tfoot>` rows
    var tr = Array.prototype.slice.call(tb.rows, 0); // put rows into array

    var fn = dtype === "numeric" ? function(a, b) {
      return parseFloat(a.cells[n].textContent) <= parseFloat(b.cells[n].textContent) ? -1 : 1;
    } : function(a, b) {
      var c = a.cells[n].textContent.trim().localeCompare(b.cells[n].textContent.trim());
      return c > 0 ? 1 : (c < 0 ? -1 : 0);
    };
    var isSorted = function(array, fn) {
      if (array.length < 2) {
        return 1;
      }
      var direction = fn(array[0], array[1]);
      for (var i = 1; i < array.length - 1; ++i) {
        var d = fn(array[i], array[i + 1]);
        if (d === 0) {
          continue;
        } else if (direction === 0) {
          direction = d;
        } else if (direction !== d) {
          return 0;
        }
      }
      return direction;
    };

    var sorted = isSorted(tr, fn);
    var i;

    if (sorted === 1 || sorted === -1) {
      // if sorted already, reverse it
      for (i = tr.length - 1; i >= 0; --i) {
        tb.appendChild(tr[i]); // append each row in order
      }
    } else {
      tr = tr.sort(fn);
      for (i = 0; i < tr.length; ++i) {
        tb.appendChild(tr[i]); // append each row in order
      }
    }
  };

  function save_kernel_info() {
    var used_kernels = new Set();
    var cells = nb.get_cells();
    for (var i = cells.length - 1; i >= 0; --i) {
      if (cells[i].cell_type === "code" && cells[i].metadata.kernel) {
        used_kernels.add(cells[i].metadata.kernel);
      }
    }
    nb.metadata["sos"]["kernels"] = Array.from(used_kernels).sort().map(
      function(x) {
        return [window.DisplayName[x], window.KernelName[x],
          window.LanguageName[x] || "", window.BackgroundColor[x] || ""
        ]
      }
    );
    // if some kernel is not registered add them
  }

  // detect if the code contains notebook-involved magics such as %sosrun, sossave, preview
  function hasWorkflowMagic(code) {
    let lines = code.split("\n");
    for (let l = 0; l < lines.length; ++l) {
      // ignore starting comment, new line and ! lines
      if (lines[l].startsWith("#") || lines[l].trim() === "" || lines[l].startsWith("!")) {
        continue;
      }
      // other magic
      if (lines[l].startsWith("%")) {
        if (lines[l].match(/^%sosrun($|\s)|^%run($|\s)|^%sossave($|\s)|^%preview\s.*(-w|--workflow).*$/)) {
          return true;
        }
      } else {
        return false;
      }
    }
  }

  // get the workflow part of text from a cell
  function getCellWorkflow(cell) {
    var lines = cell.get_text().split("\n");
    var workflow = "";
    var l;
    for (l = 0; l < lines.length; ++l) {
      if (lines[l].startsWith("%include") || lines[l].startsWith("%from")) {
        workflow += lines[l] + "\n";
        continue;
      } else if (lines[l].startsWith("#") || lines[l].startsWith("%") || lines[l].trim() === "" || lines[l].startsWith("!")) {
        continue;
      } else if (lines[l].startsWith("[") && lines[l].endsWith("]")) {
        workflow += lines.slice(l).join("\n") + "\n\n";
        break;
      }
    }
    return workflow;
  }

  // get workflow from notebook
  function getNotebookWorkflow(cells) {
    let workflow = '#!/usr/bin/env sos-runner\n#fileformat=SOS1.0\n\n';
    for (let i = 0; i < cells.length; ++i) {
      let cell = cells[i];
      if (cell.cell_type === "code" && (!cell.metadata['kernel'] || cell.metadata['kernel'] === "SoS")) {
        workflow += getCellWorkflow(cell);
      }
    }
    return workflow;
  }


  var my_execute = function(code, callbacks, options) {
    /* check if the code is a workflow call, which is marked by
     * %sosrun or %sossave workflowname with options
     */
    options.sos = {}
    var run_notebook = hasWorkflowMagic(code);
    var cells = nb.get_cells();
    if (run_notebook) {
      // Running %sossave --to html needs to save notebook
      nb.save_notebook();
      options.sos.workflow = getNotebookWorkflow(cells);
    }
    options.sos.path = nb.notebook_path;
    options.sos.use_panel = nb.metadata["sos"]["panel"].displayed;
    options.sos.default_kernel = nb.metadata["sos"].default_kernel;
    options.sos.rerun = false;
    for (var i = cells.length - 1; i >= 0; --i) {
      // this is the cell that is being executed...
      // according to this.set_input_prompt("*") before execute is called.
      // also, because a cell might be starting without a previous cell
      // being finished, we should start from reverse and check actual code
      if (cells[i].input_prompt_number === "*" && code === cells[i].get_text()) {
        // use cell kernel if meta exists, otherwise use nb.metadata["sos"].default_kernel
        if (window._auto_resume) {
          options.sos.rerun = true;
          window._auto_resume = false;
        }
        options.sos.cell_id = cells[i].cell_id;
        options.sos.cell_kernel = cells[i].metadata.kernel;
        return this.orig_execute(code, callbacks, options);
      }
    }
    options.sos.cell_kernel = window.my_panel.cell.metadata.kernel;
    options.sos.cell_id = '';
    options.silent = false;
    options.store_history = false;
    // if this is a command from scratch pad (not part of the notebook)
    return this.orig_execute(code, callbacks, options);
  };

  function loadFiles(files, fn) {
    if (!files.length) {
      files = [];
    }
    var head = document.head || document.getElementsByTagName("head")[0];

    function loadFile(index) {
      if (files.length > index) {
        var fileref;
        if (files[index].endsWith(".css")) {
          fileref = document.createElement("link");
          fileref.setAttribute("rel", "stylesheet");
          fileref.setAttribute("type", "text/css");
          fileref.setAttribute("href", files[index]);
        } else {
          fileref = document.createElement("script");
          fileref.setAttribute("type", "text/javascript");
          fileref.setAttribute("src", files[index]);
        }
        head.appendChild(fileref);
        // Used to call a callback function
        fileref.onload = function() {
          loadFile(index);
        };
        index = index + 1;
      } else if (fn) {
        fn();
      }
    }
    loadFile(0);
  }

  function get_cell_by_id(id) {
    if (id) {
      return nb.get_cells().find(cell => cell.cell_id === id);
    } else {
      return window.my_panel.cell;
    }
  }

  function changeStyleOnKernel(cell, type) {
    // type should be  displayed name of kernel
    var sel = cell.element[0].getElementsByClassName("cell_kernel_selector")[0];
    if (!type) {
      sel.selectedIndex = -1;
    } else {
      var opts = sel.options;
      var opt, j;
      for (j = 0; opt = opts[j]; j++) {
        if (opt.value === window.DisplayName[type]) {
          sel.selectedIndex = j;
          break;
        }
      }
    }

    if (cell.metadata.tags && cell.metadata.tags.indexOf("report_output") >= 0) {
      $(".output_wrapper", cell.element).addClass("report_output");
    } else {
      $(".output_wrapper", cell.element).removeClass("report_output");
    }

    // cell in panel does not have prompt area
    var col = "";
    if (cell.is_panel) {
      if (type && window.BackgroundColor[type]) {
        col = window.BackgroundColor[type];
      }
      cell.element[0].getElementsByClassName("input")[0].style.backgroundColor = col;
      cell.user_highlight = {
        name: 'sos',
        base_mode: window.LanguageName[type] || window.KernelName[type] || type,
      };
      //console.log(`Set cell code mirror mode to ${cell.user_highlight}`)
      cell.code_mirror.setOption('mode', cell.user_highlight);
      return col;
    }

    if (type === "sos" && getCellWorkflow(cell)) {
      col = "#F0F0F0";
    } else if (type && window.BackgroundColor[type]) {
      col = window.BackgroundColor[type];
    }
    var ip = cell.element[0].getElementsByClassName("input_prompt");
    var op = cell.element[0].getElementsByClassName("out_prompt_overlay");
    if (ip.length > 0) {
      ip[0].style.backgroundColor = col;
    }
    if (op.length > 0) {
      op[0].style.backgroundColor = col;
    }
    var base_mode = window.LanguageName[type] || window.KernelName[type] || type;
    if (!base_mode || base_mode.toLowerCase() === 'sos') {
      cell.user_highlight = 'auto';
      cell.code_mirror.setOption('mode', 'sos');
    } else {
      cell.user_highlight = {
        name: 'sos',
        base_mode: base_mode
      }
      cell.code_mirror.setOption('mode', cell.user_highlight);
    }
    //console.log(`Set cell code mirror mode to ${cell.user_highlight.base_mode}`)
    return col;
  }


  function load_select_kernel() {
    // this function will be called twice, the first time when the notebook is loaded
    // to create UT elements using the information from notebook metadata. The second
    // time will be caused whent the backend sends the frontend a list of available kernels
    // this is why we should not add additional UI elements when the function is called
    // the second time.

    var i = 0;
    var cells = nb.get_cells();
    for (i = 0; i < cells.length; i++) {
      add_lan_selector(cells[i], cells[i].metadata.kernel);
    }
    if (window.my_panel) {
      add_lan_selector(window.my_panel.cell, "SoS");
    }

    cells = nb.get_cells();
    for (i = 0; i < cells.length; i++) {
      if (cells[i].cell_type === "code") {
        changeStyleOnKernel(cells[i], cells[i].metadata.kernel);
      }
    }
    // update droplist of panel cell
    if (window.my_panel) {
      changeStyleOnKernel(window.my_panel.cell);
    }

    var dropdown = $("<select></select>").attr("id", "kernel_selector")
      .css("margin-left", "0.75em")
      .attr("class", "form-control select-xs");
    // .change(select_kernel);
    if (Jupyter.toolbar.element.has("#kernel_selector").length === 0) {
      Jupyter.toolbar.element.append(dropdown);
    }
    // remove any existing items
    $("#kernel_selector").empty();
    $.each(window.KernelList, function(key, value) {
      $("#kernel_selector")
        .append($("<option/>")
          .attr("value", window.DisplayName[value[0]])
          .text(window.DisplayName[value[0]]));
    });
    $("#kernel_selector").val(nb.metadata.sos.default_kernel);
    $("#kernel_selector").change(function() {
      var kernel_type = $("#kernel_selector").val();

      nb.metadata["sos"].default_kernel = kernel_type;

      var cells = nb.get_cells();
      for (var i in cells) {
        if (cells[i].cell_type === "code" && !cells[i].metadata.kernel) {
          changeStyleOnKernel(cells[i], undefined);
        }
      }
    });
  }

  var show_toc = function(evt) {
    var cell = window.my_panel.cell;
    cell.clear_input();
    cell.set_text("%toc");
    cell.clear_output();
    var toc = cell.output_area.create_output_area().append(table_of_contents());
    cell.output_area._safe_append(toc);
    adjustPanel();
  };

  function register_sos_comm() {
    // comm message sent from the kernel
    window.sos_comm = Jupyter.notebook.kernel.comm_manager.new_comm("sos_comm", {});
    window.sos_comm.on_msg(function(msg) {
      // when the notebook starts it should receive a message in the format of
      // a nested array of elements such as
      //
      // "ir", "R", "#ABackgroundColorDEF"
      //
      // where are kernel name (jupyter kernel), displayed name (SoS), and background
      // color assigned by the language module. The user might use name ir or R (both
      // acceptable) but the frontend should only display displayed name, and send
      // the real kernel name back to kernel (%frontend and metadata).
      //
      // there are two kinds of messages from my_execute
      // 1. cell_idx: kernel
      //     the kernel used for the cell with source
      // 2. None: kernel
      //     the kernel for the new cell

      var data = msg.content.data;
      var msg_type = msg.metadata.msg_type;
      var i, j;
      var k_idx;
      var cell;

      if (msg_type === "kernel-list") {
        /*
        for (j = 0; j < nb.metadata["sos"]["kernels"].length; j++) {
            var kdef = nb.metadata["sos"]["kernels"][j];
            // if local environment has kernel, ok...
            k_idx = data.findIndex((item) => item[0] === kdef[0]);
            // otherwise is the kernel actually used?
            if (k_idx === -1) {
                alert("subkernel " + kdef[0] + " defined in this notebook (kernel " + kdef[1] + " and language " + kdef[2] +
                    ") is unavailable.");
            }
        }
        */

        for (i = 0; i < data.length; i++) {
          // BackgroundColor is color
          window.BackgroundColor[data[i][0]] = data[i][3];
          // by kernel name? For compatibility ...
          if (!(data[i][1] in window.BackgroundColor)) {
            window.BackgroundColor[data[i][1]] = data[i][3];
          }
          // DisplayName
          window.DisplayName[data[i][0]] = data[i][0];
          if (!(data[i][1] in window.DisplayName)) {
            window.DisplayName[data[i][1]] = data[i][0];
          }
          // Name
          window.KernelName[data[i][0]] = data[i][1];
          if (!(data[i][1] in window.KernelName)) {
            window.KernelName[data[i][1]] = data[i][1];
          }
          // Language Name
          window.LanguageName[data[i][0]] = data[i][2];
          if (!(data[i][2] in window.LanguageName)) {
            window.LanguageName[data[i][2]] = data[i][2];
          }
          // KernelList, use displayed name
          if (window.KernelList.findIndex((item) => item[0] === data[i][0]) === -1) {
            window.KernelList.push([data[i][0], data[i][0]]);
          }
          // if options ...
          if (data[i].length > 4) {
            window.KernelOptions[data[i][0]] = data[i][4];
          }

          // if the kernel is in metadata, check conflict
          k_idx = nb.metadata["sos"]["kernels"].findIndex((item) => item[0] === data[i][0]);
          if (k_idx !== -1) {
            var r;
            // if kernel exist update the rest of the information, but warn users first on
            // inconsistency
            if (nb.metadata["sos"]["kernels"][k_idx][1] !== data[i][1] && nb.metadata["sos"]["kernels"][k_idx][1]) {
              r = confirm("This notebook used Jupyter kernel " + nb.metadata["sos"]["kernels"][k_idx][1] + " for subkernel " + data[i][0] + ". Do you want to switch to " + data[i][1] + " instead?");
              if (!r) {
                window.KernelName[data[i][0]] = nb.metadata["sos"]["kernels"][k_idx][1];
              }
            }
            if (nb.metadata["sos"]["kernels"][k_idx][2] !== data[i][2] && nb.metadata["sos"]["kernels"][k_idx][2]) {
              if (data[i][2] !== "") {
                r = confirm("This notebook used language definition " + nb.metadata["sos"]["kernels"][k_idx][2] + " for subkernel " + data[i][0] + ". Do you want to switch to " + data[i][2] + " instead?");
                if (!r) {
                  window.LanguageName[data[i]][0] = nb.metadata["sos"]["kernels"][k_idx][2];
                }
              }
            }
          }
        }
        //add dropdown menu of kernels in frontend
        load_select_kernel();
        console.log("kernel list updated");
      } else if (msg_type === "default-kernel") {
        // update the cells when the notebook is being opened.
        // we also set a global kernel to be used for new cells
        $("#kernel_selector").val(window.DisplayName[data]);
        // a side effect of change is cells without metadata kernel info will change background
        $("#kernel_selector").change();
      } else if (msg_type === "cell-kernel") {
        // get cell from passed cell index, which was sent through the
        // %frontend magic

        cell = get_cell_by_id(data[0]);
        if (cell.metadata.kernel !== window.DisplayName[data[1]]) {
          cell.metadata.kernel = window.DisplayName[data[1]];
          // set meta information
          changeStyleOnKernel(cell, data[1]);
          save_kernel_info();
        } else if (cell.metadata.tags && cell.metadata.tags.indexOf("report_output") >= 0) {
          // #639
          // if kernel is different, changeStyleOnKernel would set report_output.
          // otherwise we mark report_output
          $(".output_wrapper", cell.element).addClass("report_output");
        }
      } else if (msg_type === "preview-input") {
        cell = window.my_panel.cell;
        cell.clear_input();
        cell.set_text(data);
        cell.clear_output();
      } else if (msg_type === "preview-kernel") {
        changeStyleOnKernel(window.my_panel.cell, data);
      } else if (msg_type === "highlight-workflow") {
        //cell = window.my_panel.cell;
        //cell.clear_input();
        //cell.set_text("%preview --workflow");
        //cell.clear_output();
        //cell.output_area.append_output({
        //    "output_type": "display_data",
        //    "metadata": {},
        //    "data": {
        //             "text/html": "<textarea id='panel_preview_workflow'>" + data + "</textarea>"
        //    }
        //});
        // <textarea id="side_panel_code">{}</textarea>'
        CodeMirror.fromTextArea(document.getElementById(data), {
          "mode": "sos",
          "theme": "ipython"
        })
      } else if (msg_type === "tasks-pending") {
        // console.log(data);
        /* we record the pending tasks of cells so that we could
           rerun cells once all tasks have been completed */
        /* let us get a more perminant id for cell so that we
           can still locate the cell once its tasks are completed. */
        cell = get_cell_by_id(data[0]);
        window.pending_cells[cell.cell_id] = data[1];
      } else if (msg_type === "remove-task") {
        var item = document.getElementById("table_" + data[0] + "_" + data[1]);
        if (item) {
          item.parentNode.removeChild(item);
        }
      } else if (msg_type === "update-duration") {
        if (!window._duration_updater) {
          window._duration_updater = window.setInterval(function() {
            $("[id^=duration_]").text(function() {
              if ($(this).attr("class") != "running")
                return $(this).text();
              return window.durationFormatter($(this).attr("datetime"));
            });
          }, 5000);
        }
      } else if (msg_type === "task-status") {
        // console.log(data);
        var item = document.getElementById("status_" + data[0] + "_" + data[1]);
        if (!item) {
          return;
        } else {
          // id, status, status_class, action_class, action_func
          item.className = "fa fa-fw fa-2x " + data[3];
          item.setAttribute("onmouseover", "$('#status_" + data[0] + "_" + data[1] + "').addClass('" + data[4] + " task_hover').removeClass('" + data[3] + "')");
          item.setAttribute("onmouseleave", "$('#status_" + data[0] + "_" + data[1] + "').addClass('" + data[3] + "').removeClass('" + data[4] + " task_hover')");
          item.setAttribute("onClick", data[5] + "('" + data[1] + "', '" + data[0] + "')");
        }
        var item = document.getElementById("duration_" + data[0] + "_" + data[1]);
        if (item) {
          item.className = data[2];
          // stop update and reset time ...
          if (data[2] != "running") {
            var curTime = new Date();
            item.innerText = window.durationFormatter(item.getAttribute("datetime"));
            item.setAttribute('datetime', curTime.getTime());
          }
        }
        if (data[2] === "completed") {
          /* if successful, let us re-run the cell to submt another task
             or get the result */
          for (cell in window.pending_cells) {
            /* remove task from pending_cells */
            for (var idx = 0; idx < window.pending_cells[cell].length; ++idx) {
              if (window.pending_cells[cell][idx][0] !== data[0] ||
                window.pending_cells[cell][idx][1] !== data[1]) {
                continue;
              }
              window.pending_cells[cell].splice(idx, 1);
              if (window.pending_cells[cell].length === 0) {
                delete window.pending_cells[cell];
                /* if the does not have any pending one, re-run it. */
                var cells = nb.get_cells();
                var rerun = null;
                for (i = 0; i < cells.length; ++i) {
                  if (cells[i].cell_id === cell) {
                    rerun = cells[i];
                    break;
                  }
                }
                if (rerun) {
                  window._auto_resume = true;
                  rerun.execute();
                }
                break;
              }
            }
          }
        }
      } else if (msg_type === "show_toc") {
        show_toc();
      } else if (msg_type === "paste-table") {
        var cm = nb.get_selected_cell().code_mirror;
        cm.replaceRange(data, cm.getCursor());
      } else if (msg_type === 'alert') {
        alert(data);
      } else if (msg_type === 'notebook-version') {
        // right now no upgrade, just save version to notebook
        nb.metadata["sos"]["version"] = data;
      } else if (msg_type === 'clear-output') {
        // console.log(data)
        var active = nb.get_selected_cells_indices();
        var clear_task = function(cell, status) {
          var status_element = cell.element[0].getElementsByClassName(status);
          while (status_element.length > 0) {
            var table_element = status_element[0].parentNode.parentNode.parentNode.parentNode;
            // remove the table
            if (table_element.className == 'task_table') {
              table_element.parentElement.remove(table_element);
            }
          }
        }
        var clear_class = function(cell, element_class) {
          var elements = cell.element[0].getElementsByClassName(element_class);
          while (elements.length > 0) {
            elements[0].parentNode.removeChild(elements[0]);
            elements = cell.element[0].getElementsByClassName(element_class);
          }
        }
        // if remove all
        if (data[1]) {
          var cells = nb.get_cells();
          var i;
          var j;
          for (i = 0; i < cells.length; ++i) {
            if (cells[i].cell_type != "code")
              continue;
            if (data[2]) {
              for (j = 0; j < data[2].length; ++j) {
                clear_task(cells[i], data[2][j]);
              }
            } else if (data[3]) {
              for (j = 0; j < data[3].length; ++j) {
                clear_class(cells[i], data[3][j]);
              }
            } else {
              cells[i].clear_output();
            }
          }
        } else if (data[0] === "") {
          // clear output of selected cells
          var i;
          var j;
          for (i = 0; i < active.length; ++i) {
            if (nb.get_cell(active[i]).cell_type != "code")
              continue;
            if (data[2]) {
              for (j = 0; j < data[2].length; ++j) {
                clear_task(nb.get_cell(active[i]), data[2][j]);
              }
            } else if (data[3]) {
              for (j = 0; j < data[3].length; ++j) {
                clear_class(nb.get_cell(active[i]), data[3][j]);
              }
            } else {
              nb.get_cell(active[i]).clear_output();
            }
          }
        } else if (get_cell_by_id(data[0]).cell_type === "code") {
          // clear current cell
          var j;
          if (data[2]) {
            for (j = 0; j < data[2].length; ++j) {
              clear_task(get_cell_by_id(data[0]), data[2][j]);
            }
          } else if (data[3]) {
            for (j = 0; j < data[3].length; ++j) {
              clear_class(get_cell_by_id(data[0]), data[3][j]);
            }
          } else {
            get_cell_by_id(data[0]).clear_output();
          }
        }
        if (active.length > 0) {
          nb.select(active[0]);
        }
      } else {
        // this is preview output
        cell = window.my_panel.cell;
        data.output_type = msg_type;
        cell.output_area.append_output(data);
      }
      adjustPanel();
    });

    window.sos_comm.send({
      "list-kernel": nb.metadata["sos"]["kernels"],
      "update-task-status": window.unknown_tasks,
      "notebook-version": nb.metadata["sos"]["version"] || "undefined",
    });
    console.log("sos comm registered");
  }

  function send_kernel_msg(msg) {
    window.sos_comm.send(msg);
  }

  function wrap_execute() {
    // override kernel execute with the wrapper.
    // however, this function can be called multiple times for kernel
    // restart etc, so we should be careful
    if (!nb.kernel.orig_execute) {
      nb.kernel.orig_execute = nb.kernel.execute;
      nb.kernel.execute = my_execute;
      console.log("executor patched");
    }
  }


  window.kill_task = function(task_id, task_queue) {
    console.log("Kill " + task_id);
    send_kernel_msg({
      "kill-task": [task_id, task_queue],
    });
  };

  window.resume_task = function(task_id, task_queue) {
    console.log("Resume " + task_id);
    send_kernel_msg({
      "resume-task": [task_id, task_queue],
    });
  };

  window.task_info = function(task_id, task_queue) {
    console.log("Request info on " + task_id);
    send_kernel_msg({
      "task-info": [task_id, task_queue],
    });
    var cell = window.my_panel.cell;
    cell.clear_input();
    cell.set_text("%taskinfo " + task_id + " -q " + task_queue);
    cell.clear_output();
  };

  window.durationFormatter = function(start_date) {
    var ms = new Date() - start_date;
    var res = [];
    var seconds = parseInt(ms / 1000);
    var day = Math.floor(seconds / 86400);
    if (day > 0) {
      res.push(day + " day");
    }
    var hh = Math.floor((seconds % 86400) / 3600);
    if (hh > 0) {
      res.push(hh + " hr");
    }
    var mm = Math.floor((seconds % 3600) / 60);
    if (mm > 0) {
      res.push(mm + " min");
    }
    var ss = seconds % 60;
    if (ss > 0) {
      res.push(ss + " sec");
    }
    res = res.join(" ");
    if (res === "") {
      return "0 sec";
    } else {
      return res;
    }
  };

  function enable_fold_gutter(cell) {
    var matched = cell.get_text().match(/[\n\r][ \t]/g);
    // if at least three lines has identation because there is no actual benefit
    // of wrapping short paragraphs
    if (matched && matched.length > 2) {
      cell.code_mirror.setOption("gutters", ["CodeMirror-foldgutter"]);
      cell.code_mirror.setOption("foldGutter", true);
    } else {
      cell.code_mirror.setOption("gutters", []);
      cell.code_mirror.setOption("foldGutter", false);
    }
  };

  function set_codemirror_option(evt, param) {
    var cells = nb.get_cells();
    var i;
    for (i = cells.length - 1; i >= 0; --i) {
      cells[i].code_mirror.setOption("styleActiveLine", cells[i].selected);
    }
    enable_fold_gutter(param.cell);
    return true;
  }

  function changeCellStyle() {
    var cells = nb.get_cells();
    // setting up background color and selection according to notebook metadata
    var i;
    for (i in cells) {
      if (cells[i].cell_type === "code") {
        changeStyleOnKernel(cells[i], cells[i].metadata.kernel);
      }
    }
    $("[id^=status_]").removeAttr("onClick").removeAttr("onmouseover").removeAttr("onmouseleave");
    var tasks = $("[id^=status_]");
    window.unknown_tasks = [];
    for (i = 0; i < tasks.length; ++i) {
      // status_localhost_5ea9232779ca1959
      if (tasks[i].id.match("^status_[^_]+_[0-9a-f]{16,32}$")) {
        tasks[i].className = "fa fa-fw fa-2x fa-refresh fa-spin";
        window.unknown_tasks.push(tasks[i].id);
      }
    }
  }


  function incr_lbl(ary, h_idx) { //increment heading label  w/ h_idx (zero based)
    ary[h_idx]++;
    for (var j = h_idx + 1; j < ary.length; j++) {
      ary[j] = 0;
    }
    return ary.slice(0, h_idx + 1);
  }

  function removeMathJaxPreview(elt) {
    elt.find("script[type='math/tex']").each(
      function(i, e) {
        $(e).replaceWith("$" + $(e).text() + "$");
      });
    elt.find("span.MathJax_Preview").remove();
    elt.find("span.MathJax").remove();
    return elt;
  }


  function highlight_toc_item(evt, data) {
    if ($(".toc").length === 0) {
      return;
    }
    var c = data.cell.element; //
    if (c) {
      var ll = $(c).find(":header");
      if (ll.length === 0) {
        ll = $(c).prevAll().find(":header");
      }
      var elt = ll[ll.length - 1];
      if (elt) {
        var highlighted_item = $(".toc").find('a[href="#' + elt.id + '"]');
        if (evt.type === "execute") {
          // remove the selected class and add execute class
          // il the cell is selected again, it will be highligted as selected+running
          highlighted_item.removeClass("toc-item-highlight-select").addClass("toc-item-highlight-execute");
          //console.log("->>> highlighted_item class",highlighted_item.attr("class"))
        } else {
          $(".toc").find(".toc-item-highlight-select").removeClass("toc-item-highlight-select");
          highlighted_item.addClass("toc-item-highlight-select");
        }
      }
    }
  }


  var make_link = function(h) {
    var a = $("<a/>");
    a.attr("href", "#" + h.attr("id"));
    // get the text *excluding* the link text, whatever it may be
    var hclone = h.clone();
    hclone = removeMathJaxPreview(hclone);
    hclone.children().last().remove(); // remove the last child (that is the automatic anchor)
    hclone.find("a[name]").remove(); //remove all named anchors
    a.html(hclone.html());
    a.on("click", function() {
      setTimeout(function() {
        $.ajax();
      }, 100); //workaround for  https://github.com/jupyter/notebook/issues/699
      nb.get_selected_cell().unselect(); //unselect current cell
      var new_selected_cell = $("[id='" + h.attr('id') + "']").parents('.unselected').switchClass('unselected', 'selected');
      new_selected_cell.data("cell").selected = true;
      var cell = new_selected_cell.data("cell") // nb.get_selected_cell()
      highlight_toc_item("toc_link_click", {
        cell: cell
      });
    });
    return a;
  };


  var table_of_contents = function() {

    //process_cell_toc();

    var toc = $("<div class='toc'/>");
    var ul = $("<ul/>").addClass("toc-item").addClass("lev1").attr("id", "toc-level0");
    toc.append(ul);
    var depth = 1; //var depth = ol_depth(ol);
    var li = ul; //yes, initialize li with ul!
    var all_headers = $("#notebook").find(":header");
    var min_lvl = 1;
    var lbl_ary = [];
    for (; min_lvl <= 6; min_lvl++) {
      if (all_headers.is("h" + min_lvl)) {
        break;
      }
    }
    for (var i = min_lvl; i <= 6; i++) {
      lbl_ary[i - min_lvl] = 0;
    }

    //loop over all headers
    all_headers.each(function(i, h) {
      var level = parseInt(h.tagName.slice(1), 10) - min_lvl + 1;
      // skip headings with no ID to link to
      if (!h.id) {
        return;
      }
      //If h had already a number, remove it
      /* $(h).find(".toc-item-num").remove(); */
      var num_str = incr_lbl(lbl_ary, level - 1).join("."); // numbered heading labels
      //var num_lbl = $("<span/>").addClass("toc-item-num")
      //    .text(num_str).append("&nbsp;").append("&nbsp;");

      // walk down levels
      for (var elm = li; depth < level; depth++) {
        var new_ul = $("<ul/>").addClass("lev" + (depth + 1).toString()).addClass("toc-item");
        elm.append(new_ul);
        elm = ul = new_ul;
      }
      // walk up levels
      for (; depth > level; depth--) {
        // up twice: the enclosing <ol> and <li> it was inserted in
        ul = ul.parent();
        while (!ul.is("ul")) {
          ul = ul.parent();
        }
      }
      // Change link id -- append current num_str so as to get a kind of unique anchor
      // A drawback of this approach is that anchors are subject to change and thus external links can fail if toc changes
      // Anyway, one can always add a <a name="myanchor"></a> in the heading and refer to that anchor, eg [link](#myanchor)
      // This anchor is automatically removed when building toc links. The original id is also preserved and an anchor is created
      // using it.
      // Finally a heading line can be linked to by [link](#initialID), or [link](#initialID-num_str) or [link](#myanchor)
      h.id = h.id.replace(/\$/g, "").replace("\\", "");
      if (!$(h).attr("saveid")) {
        $(h).attr("saveid", h.id)
      } //save original id
      h.id = $(h).attr("saveid") + "-" + num_str.replace(/\./g, "");
      // change the id to be "unique" and toc links to it
      // (and replace "." with "" in num_str since it poses some pb with jquery)
      var saveid = $(h).attr("saveid")
      //escape special chars: http://stackoverflow.com/questions/3115150/
      var saveid_search = saveid.replace(/[-[\]{}():\/!;&@=$£%§<>%"'*+?.,~\\^$|#\s]/g, "\\$&");
      if ($(h).find("a[name=" + saveid_search + "]").length === 0) { //add an anchor with original id (if it does not already exists)
        $(h).prepend($("<a/>").attr("name", saveid));
      }


      // Create toc entry, append <li> tag to the current <ol>. Prepend numbered-labels to headings.
      li = $("<li/>").append(make_link($(h)));

      ul.append(li);
      // $(h).prepend(num_lbl);
    });
    return toc;
  };

  var create_panel_div = function() {
    var panel_wrapper = $("<div id='panel-wrapper'/>")
      .append(
        $("<div/>").attr("id", "panel").addClass("panel")
      );

    $("body").append(panel_wrapper);

    $([Jupyter.events]).on("resize-header.Page", function() {
      if (nb.metadata["sos"]["panel"].style === "side") {
        $("#panel-wrapper").css("top", $("#header").height());
        $("#panel-wrapper").css("height", $("#site").height());
      }
    });
    $([Jupyter.events]).on("toggle-all-headers", function() {
      if (nb.metadata["sos"]["panel"].style === "side") {
        var headerVisibleHeight = $("#header").is(":visible") ? $("#header").height() : 0;
        $("#panel-wrapper").css("top", headerVisibleHeight);
        $("#panel-wrapper").css("height", $("#site").height());
      }
    });

    $(".output_scroll").on("resizeOutput", function() {
      var output = $(this);
      setTimeout(function() {
        output.scrollTop(output.prop("scrollHeight"));
      }, 0);
    });

    // enable dragging and save position on stop moving
    $("#panel-wrapper").draggable({

      drag: function(event, ui) {

        // If dragging to the left side, then transforms in sidebar
        if ((ui.position.left <= 0) && (nb.metadata["sos"]["panel"].style === "float")) {
          nb.metadata["sos"]["panel"].style = "side";
          nb.metadata["sos"]["panel"].height = $("#panel-wrapper").css("height");
          panel_wrapper.removeClass("float-wrapper").addClass("sidebar-wrapper");
          $("#notebook-container").css("margin-left", $("#panel-wrapper").width() + 30);
          $("#notebook-container").css("width", $("#notebook").width() - $("#panel-wrapper").width() - 30);
          ui.position.top = $("#header").height();
          ui.position.left = 0;
          $("#panel-wrapper").css("height", $("#site").height());
        }
        if (ui.position.left <= 0) {
          ui.position.left = 0;
          ui.position.top = $("#header").height();
        }
        if ((ui.position.left > 0) && (nb.metadata["sos"]["panel"].style === "side")) {
          nb.metadata["sos"]["panel"].style = "float";
          if (nb.metadata["sos"]["panel"].height === 0) {
            nb.metadata["sos"]["panel"].height = Math.max($("#site").height() / 2, 200);
          }
          $("#panel-wrapper").css("height", nb.metadata["sos"]["panel"].height);
          panel_wrapper.removeClass("sidebar-wrapper").addClass("float-wrapper");
          $("#notebook-container").css("margin-left", 30);
          $("#notebook-container").css("width", $("#notebook").width() - 30);
        }

      }, //end of drag function
      start: function(event, ui) {
        $(this).width($(this).width());
      },
      stop: function(event, ui) {
        // Ensure position is fixed (again)
        $("#panel-wrapper").css("position", "fixed");
      },
      // can only drag from the border, not the panel and the cell. This
      // allows us to, for example, copy/paste output area.
      cancel: "#panel, #input"
    });

    $("#panel-wrapper").resizable({
      resize: function(event, ui) {
        if (nb.metadata["sos"]["panel"].style === "side") {
          $("#notebook-container").css("margin-left", $("#panel-wrapper").width() + 30);
          $("#notebook-container").css("width", $("#notebook").width() - $("#panel-wrapper").width() - 30);
        }
      },
      start: function(event, ui) {
        $(this).width($(this).width());
        //$(this).css("position", "fixed");
      },
    });

    // Ensure position is fixed
    $("#panel-wrapper").css("position", "fixed");

    // if panel-wrapper is undefined (first run(?), then hide it)
    // if ($("#panel-wrapper").css("display") === undefined) $("#panel-wrapper").css("display", "none") //block
    if (!$("#panel-wrapper").css("display")) {
      $("#panel-wrapper").css("display", "block"); //block
    }
    $("#site").bind("siteHeight", function() {
      $("#panel-wrapper").css("height", $("#site").height());
    });

    $("#site").trigger("siteHeight");


    if (nb.metadata["sos"]["panel"].style === "side") {
      $("#panel-wrapper").addClass("sidebar-wrapper");
      setTimeout(function() {
        $("#notebook-container").css("width", $("#notebook").width() - $("#panel-wrapper").width() - 30);
        $("#notebook-container").css("margin-left", $("#panel-wrapper").width() + 30);
      }, 500);
      setTimeout(function() {
        $("#panel-wrapper").css("height", $("#site").height());
      }, 500);
      setTimeout(function() {
        $("#panel-wrapper").css("top", $("#header").height());
      }, 500); //wait a bit
      $("#panel-wrapper").css("left", 0);

    }


    $(window).resize(function() {
      $("#panel").css({
        maxHeight: $(window).height() - 30
      });
      $("#panel-wrapper").css({
        maxHeight: $(window).height() - 10
      });

      if (nb.metadata["sos"]["panel"].style === "side") {
        if ($("#panel-wrapper").css("display") !== "block") {
          $("#notebook-container").css("margin-left", 30);
          $("#notebook-container").css("width", $("#notebook").width() - 30);
        } else {
          $("#notebook-container").css("margin-left", $("#panel-wrapper").width() + 30);
          $("#notebook-container").css("width", $("#notebook").width() - $("#panel-wrapper").width() - 30);
          $("#panel-wrapper").css("height", $("#site").height());
          $("#panel-wrapper").css("top", $("#header").height());
        }
      } else {
        $("#notebook-container").css("margin-left", 30);
        $("#notebook-container").css("width", $("#notebook").width() - 30);
      }
    });
    $(window).trigger("resize");
  }

  var panel = function(nb) {
    var panel = this;
    this.notebook = nb;
    this.kernel = nb.kernel;
    this.km = nb.keyboard_manager;

    create_panel_div();
    console.log("panel created");

    // create my cell
    var cell = this.cell = new CodeCell(nb.kernel, {
      events: nb.events,
      config: nb.config,
      keyboard_manager: nb.keyboard_manager,
      notebook: nb,
      tooltip: nb.tooltip,
    });
    add_lan_selector(cell).css("margin-top", "-17pt").css("margin-right", "0pt");
    cell.set_input_prompt();
    cell.is_panel = true;
    $("#panel").append(this.cell.element);

    cell.render();
    cell.refresh();
    this.cell.element.hide();

    // remove cell toolbar
    $(".celltoolbar", cell.element).remove();
    $(".ctb_hideshow", cell.element).remove();
    //this.cell.element.find("code_cell").css("position", "absolute").css("top", "1.5em");
    this.cell.element.find("div.input_prompt").addClass("panel_input_prompt").text("In [-]:");
    this.cell.element.find("div.input_area").css("margin-top", "20pt")
      .prepend(
        $("<a/>").attr("href", "#").attr("id", "input_dropdown").addClass("input_dropdown")
        .append($("<i class='fa fa-caret-down'></i>"))
        .click(function() {
          var dropdown = $("#panel_history");
          var len = $("#panel_history option").length;
          if (len === 0) {
            return false;
          }
          if (dropdown.css("display") === "none") {
            dropdown.show();
            dropdown[0].size = len;
            setTimeout(function() {
              dropdown.hide();
              dropdown.val("");
            }, 8000);
          } else {
            dropdown.hide();
          }
          return false;
        })
      ).parent().append(
        $("<select></select>").attr("id", "panel_history").addClass("panel_history")
        .change(function() {
          var item = $("#panel_history").val();
          // separate kernel and input
          var sep = item.indexOf(":");
          var kernel = item.substring(0, sep);
          var text = item.substring(sep + 1);

          var panel_cell = window.my_panel.cell;
          $("#panel_history").hide();

          // set the kernel of the panel cell as the sending cell
          if (panel_cell.metadata.kernel !== kernel) {
            panel_cell.metadata.kernel = kernel;
            changeStyleOnKernel(panel_cell, kernel);
          }
          panel_cell.clear_input();
          panel_cell.set_text(text);
          panel_cell.clear_output();
          panel_cell.execute();
          return false;
        })
      );

    add_to_panel_history("sos", "%sossave --to html --force", "");
    add_to_panel_history("sos", "%preview --workflow", "");
    add_to_panel_history("sos", "%clear", "");
    add_to_panel_history("sos", "%toc", "");

    // make the font of the panel slightly smaller than the main notebook
    // unfortunately the code mirror input cell has fixed font size that cannot
    // be changed.
    this.cell.element[0].style.fontSize = "90%";
    console.log("panel rendered");

    // override ctrl/shift-enter to execute me if I'm focused instead of the notebook's cell
    var execute_and_select_action = this.km.actions.register({
      handler: $.proxy(this.execute_and_select_event, this),
    }, "panel-execute-and-select");
    var execute_action = this.km.actions.register({
      handler: $.proxy(this.execute_event, this),
    }, "panel-execute");
    var toggle_action = this.km.actions.register({
      handler: $.proxy(toggle_panel, this),
    }, "panel-toggle");

    var execute_selected_in_panel = this.km.actions.register({
      help: "run selected text in panel cell",
      handler: execute_in_panel,
    }, "execute-selected");
    var show_toc_in_panel = this.km.actions.register({
      help: "show toc in panel",
      handler: show_toc,
    }, "show-toc");
    var paste_table = this.km.actions.register({
      help: "paste table as markdown",
      handler: paste_table_as_markdown,
    }, "paste-table");
    var toggle_output = this.km.actions.register({
      help: "toggle display output in HTML",
      handler: toggle_display_output,
    }, "toggle-show-output");
    var toggle_markdown = this.km.actions.register({
      help: "toggle between markdown and code cells",
      handler: toggle_markdown_cell,
    }, "toggle-markdown");
    var shortcuts = {
      "shift-enter": execute_and_select_action,
      "ctrl-enter": execute_action,
      "ctrl-b": toggle_action,
      // It is very strange to me that other key bindings such as
      // Ctrl-e does not work as it will somehow make the
      // code_mirror.getSelection() line getting only blank string.
      "ctrl-shift-enter": execute_selected_in_panel,
      "ctrl-shift-t": show_toc_in_panel,
      "ctrl-shift-o": toggle_output,
      "ctrl-shift-v": paste_table,
      "ctrl-shift-m": toggle_markdown,
    }
    this.km.edit_shortcuts.add_shortcuts(shortcuts);
    this.km.command_shortcuts.add_shortcuts(shortcuts);

    this.cell.element.show();
    this.cell.focus_editor();
    nb.metadata["sos"]["panel"].displayed = true;
    console.log("display panel");
  };


  panel.prototype.execute_and_select_event = function(evt) {
    // if we execute statements before the kernel is wrapped
    // from other channels (update kernel list etc), wrap it now.
    wrap_execute();

    if (this.cell.element[0].contains(document.activeElement)) {
      this.cell.execute();
    } else {
      this.notebook.execute_cell_and_select_below();
    }
  };

  panel.prototype.execute_event = function(evt) {
    // if we execute statements before the kernel is wrapped
    // from other channels (update kernel list etc), wrap it now.
    wrap_execute();

    if (this.cell.element[0].contains(document.activeElement)) {
      this.cell.execute();
    } else {
      this.notebook.execute_selected_cells();
    }
  };

  var add_to_panel_history = function(kernel, text, col) {
    // console.log("add " + kernel + " " + col);
    var matched = false;
    $("#panel_history option").each(function(index, element) {
      if (element.value === kernel + ":" + text) {
        matched = true;
        return false;
      }
    })
    if (!matched) {
      $("#panel_history").prepend($("<option></option>")
          .css("background-color", col)
          .attr("value", kernel + ":" + text).text(text.split("\n").join(" .. ").truncate(40))
        )
        .prop("selectedIndex", -1);
    }
  }

  String.prototype.truncate = function() {
    var re = this.match(/^.{0,25}[\S]*/);
    var l = re[0].length;
    var re = re[0].replace(/\s$/, "");
    if (l < this.length)
      re = re + "...";
    return re;
  }

  var remove_tag = function(cell, tag) {
    // if the toolbar exists, use the button ...
    $(".output_wrapper", cell.element).removeClass(tag);
    if ($(".tags-input", cell.element).length > 0) {
      // find the button and click
      var tag = $(".cell-tag", cell.element).filter(function(idx, y) {
        return y.innerText === tag;
      });
      $(".remove-tag-btn", tag).click();
    } else {
      // otherwise just remove the metadata
      var idx = cell.metadata.tags.indexOf(tag);
      cell.metadata.tags.splice(idx, 1);
    }
  }

  var add_tag = function(cell, tag) {
    $(".output_wrapper", cell.element).addClass(tag);
    if ($(".tags-input", cell.element).length > 0) {
      var taginput = $(".tags-input", cell.element);
      taginput.children()[1].value = tag;
      $(".btn", taginput)[1].click();
    } else {
      // if tag toolbar not exist
      if (!cell.metadata.tags) {
        cell.metadata.tags = [tag];
      } else {
        cell.metadata.tags.push(tag);
      }
    }
  }

  var toggle_display_output = function(evt) {
    var cell = evt.notebook.get_selected_cell();
    if (cell.cell_type === "markdown") {
      // switch between hide_output and ""
      if (cell.metadata.tags && cell.metadata.tags.indexOf("hide_output") >= 0) {
        // if report_output on, remove it
        remove_tag(cell, "hide_output");
      } else {
        add_tag(cell, "hide_output");
      }
    } else if (cell.cell_type === "code") {
      // switch between report_output and ""
      if (cell.metadata.tags && cell.metadata.tags.indexOf("report_output") >= 0) {
        // if report_output on, remove it
        remove_tag(cell, "report_output");
      } else {
        add_tag(cell, "report_output");
      }
    }
    // evt.notebook.select_next(true);
    evt.notebook.focus_cell();
  }

  var paste_table_as_markdown = function(evt) {
    var cell = evt.notebook.get_selected_cell();
    if (cell.cell_type === "markdown") {
      send_kernel_msg({
        'paste-table': []
      })
    }
    // evt.notebook.select_next(true);
    evt.notebook.focus_cell();
  }

  var toggle_markdown_cell = function(evt) {
    var idx = evt.notebook.get_selected_index();
    if (evt.notebook.get_cell(idx).cell_type === "markdown") {
      evt.notebook.to_code(idx);
    } else {
      evt.notebook.to_markdown(idx);
    }
    evt.notebook.focus_cell();
  }

  var execute_in_panel = function(evt) {
    //var cell = nb.get_selected_cell();
    var cell = evt.notebook.get_selected_cell();
    // if the current cell does not has focus, ignore this shortcut
    if (!nb.get_selected_cell().element[0].contains(document.activeElement))
      return false;

    var text = cell.code_mirror.getSelection();
    if (text === "") {
      // get current line and move the cursor to the next line
      var cm = cell.code_mirror;
      var line_ch = cm.getCursor();
      var cur_line = line_ch["line"];
      text = cm.getLine(cur_line);
      // jump to the next non-empty line
      var line_cnt = cm.lineCount();
      while (++cur_line < line_cnt) {
        if (cm.getLine(cur_line).replace(/^\s+|\s+$/gm, "").length !== 0) {
          cell.code_mirror.setCursor(cur_line, line_ch["ch"]);
          break;
        }
      }
    }
    if (!nb.metadata["sos"]["panel"].displayed)
      toggle_panel();
    //
    var panel_cell = window.my_panel.cell;
    // change cell kernel to sending cell if sending cell is code
    if (cell.cell_type === "code") {
      // set the kernel of the panel cell as the sending cell
      var col = cell.element[0].getElementsByClassName("input_prompt")[0].style.backgroundColor;
      if (panel_cell.metadata.kernel !== cell.metadata.kernel) {
        panel_cell.metadata.kernel = cell.metadata.kernel;
        col = changeStyleOnKernel(panel_cell, panel_cell.metadata.kernel);
      }
      // if in sos mode and is single line, enable automatic preview
      var cell_kernel = cell.metadata.kernel ? cell.metadata.kernel : nb.metadata["sos"].default_kernel;
    } else {
      var cell_kernel = panel_cell.metadata.kernel ? panel_cell.metadata.kernel : nb.metadata["sos"].default_kernel;
    }
    if (KernelOptions[cell_kernel]["variable_pattern"] && text.match(KernelOptions[cell_kernel]["variable_pattern"])) {
      text = "%preview " + text;
    } else if (KernelOptions[cell_kernel]["assignment_pattern"]) {
      var matched = text.match(KernelOptions[cell_kernel]["assignment_pattern"]);
      if (matched) {
        // keep output in the panel cell...
        text = "%preview -o " + matched[1] + "\n" + text;
      }
    }
    panel_cell.clear_input();
    panel_cell.set_text(text);
    panel_cell.clear_output();
    add_to_panel_history(panel_cell.metadata.kernel, text, col);
    panel_cell.execute();
    return false;
  };


  var update_toc = function(evt, data) {
    if ($(".toc").length !== 0) {
      show_toc();
      highlight_toc_item(evt, data);
    }
  }

  function setup_panel() {
    // lazy, hook it up to Jupyter.notebook as the handle on all the singletons
    console.log("Setting up panel");
    window.my_panel = new panel(Jupyter.notebook);
  }

  function toggle_panel() {
    // toggle draw (first because of first-click behavior)
    //$("#panel-wrapper").toggle({"complete":function(){
    $("#panel-wrapper").toggle({
      "progress": function() {
        if ($("#panel-wrapper").css("display") !== "block") {
          $("#notebook-container").css("margin-left", 15);
          $("#notebook-container").css("width", $("#site").width());
        } else {
          $("#notebook-container").css("margin-left", $("#panel-wrapper").width() + 30)
          $("#notebook-container").css("width", $("#notebook").width() - $("#panel-wrapper").width() - 30)
        }
      },
      "complete": function() {
        nb.metadata["sos"]["panel"].displayed = $("#panel-wrapper").css("display") === "block"
        if (nb.metadata["sos"]["panel"].displayed) {
          console.log("panel open toc close")
          window.my_panel.cell.focus_editor();
          $("#panel-wrapper").css("z-index", 10)
        }
      }
    });
  }

  function load_panel() {

    var load_css = function() {
      var css = document.createElement("style");
      css.type = "text/css";
      css.innerHTML = `
.panel {
  padding: 0px;
  overflow-y: auto;
  font-weight: normal;
  color: #333333;
  white-space: nowrap;
  overflow-x: auto;
  height: 100%;
}

.float-wrapper {
  position: fixed !important;
  top: 120px;
  /* max-width:600px; */
  right: 20px;
  border: thin solid rgba(0, 0, 0, 0.38);
  border-radius: 5px;
  padding:5px;
  padding-top:10px;
  background-color: #F8F5E1;
  opacity: .8;
  z-index: 100;
  overflow: hidden;
}

.sidebar-wrapper {
    height: 100%;
    left: 5px;
    padding: 5px;
    padding-top: 10px;
    position: fixed !important;
    width: 25%;
    max-width: 50%;
    background-color: #F8F5E1;
    border-style: solid;
    border-color: #eeeeee;
    opacity: .99;
    overflow: hidden;
}

.col-md-9 {
  overflow:hidden;
  margin-left: 14%;
  width: 80%}

#panel-wrapper.closed {
  min-width: 100px;
  width: auto;
  transition: width;
}
#panel-wrapper:hover{
  opacity: 1;
}
#panel-wrapper .header {
  font-size: 18px;
  font-weight: bold;
}
#panel-wrapper .hide-btn {
  font-size: 14px;
  font-family: monospace;
}

#panel-wrapper .reload-btn {
  font-size: 14px;
  font-family: monospace;
}

#panel-wrapper .number_sections-btn {
  font-size: 14px;
  font-family: monospace;
}


/* dont waste so much screen space... */
#panel-wrapper .panel-item{
  padding-left: 20px;
}

#panel-wrapper .panel-item .panel-item{
  padding-left: 10px;
}

.panel-item-num {
    font-style: normal;
}

.panel-header {
    position: absolute;
    margin-left: 5pt;
    margin-top: 0.5em;
    text-align: left;
}

#panel-wrapper .prompt.input_prompt {
    padding: 0pt;
    padding-top: 0.5em;
}

#panel-wrapper .cell {
    padding: 0pt;
}

#panel-wrapper .panel-item-num {
    font-style: normal;
    font-family: Georgia, Times New Roman, Times, serif;
    color: black;
}

.toc {
  padding: 0px;
  overflow-y: auto;
  font-weight: normal;
  white-space: nowrap;
  overflow-x: auto;
}

.toc ol.toc-item {
    counter-reset: item;
    list-style: none;
    padding: 0.1em;
  }

.toc ol.toc-item li {
    display: block;
  }

.toc ul.toc-item {
    list-style-type: none;
    padding: 0;
}

.toc ol.toc-item li:before {
    font-size: 90%;
    font-family: Georgia, Times New Roman, Times, serif;
    counter-increment: item;
    content: counters(item, ".")" ";
}

.panel_input_prompt {
    position: absolute;
    min-width: 0pt;
}

.input_dropdown {
    float: right;
    margin-right: 2pt;
    margin-top: 5pt;
    z-index: 1000;
}

.panel_history {
    display: none;
    font-family: monospace;
}

.code_cell .cell_kernel_selector {
    width:70pt;
    background: none;
    z-index: 1000;
    position: absolute;
    height: 1.7em;
    margin-top: 3pt;
    right: 8pt;
    font-size: 80%;
}

.sos_hint {
    color: rgba(0,0,0,.4);
    font-family: monospace;
}

.text_cell .cell_kernel_selector {
    display: none;
}

.session_info td {
    text-align: left;
}

.session_info th {
    text-align: left;
}

.session_section {
    text-align: left;
    font-weight: bold;
    font-size: 120%;
}

.report_output {
    border-right-width: 13px;
    border-right-color: #aaaaaa;
    border-right-style: solid;
 /*   box-shadow: 13px 0px 0px #aaaaaa; */
}

.one_liner {
    overflow: hidden;
    height: 15px;
}

.one_liner:hover {
    height: auto;
    width: auto;
}

.dataframe_container { max-height: 400px }
.dataframe_input {
    border: 1px solid #ddd;
    margin-bottom: 5px;
}
.scatterplot_by_rowname div.xAxis div.tickLabel {
    transform: translateY(15px) translateX(15px) rotate(45deg);
    -ms-transform: translateY(15px) translateX(15px) rotate(45deg);
    -moz-transform: translateY(15px) translateX(15px) rotate(45deg);
    -webkit-transform: translateY(15px) translateX(15px) rotate(45deg);
    -o-transform: translateY(15px) translateX(15px) rotate(45deg);
    /*rotation-point:50% 50%;*/
    /*rotation:270deg;*/
}

.sos_dataframe td, .sos_dataframe th {
    white-space: nowrap;
}

.toc-item-highlight-select  {background-color: Gold}
.toc-item-highlight-execute  {background-color: red}
.lev1 {margin-left: 5px}
.lev2 {margin-left: 10px}
.lev3 {margin-left: 10px}
.lev4 {margin-left: 10px}
.lev5 {margin-left: 10px}
.lev6 {margin-left: 10px}
.lev7 {margin-left: 10px}
.lev8 {margin-left: 10px}

.CodeMirror-foldmarker {
  color: blue;
  text-shadow: #b9f 1px 1px 2px, #b9f -1px -1px 2px, #b9f 1px -1px 2px, #b9f -1px 1px 2px;
  font-family: arial;
  line-height: .3;
  cursor: pointer;
}
.CodeMirror-foldgutter {
  width: 1em;
}
.CodeMirror-foldgutter-open,
.CodeMirror-foldgutter-folded {
  cursor: pointer;
}
.CodeMirror-foldgutter-open:after {
  content: "\\25BE";
}
.CodeMirror-foldgutter-folded:after {
  content: "\\25B8";
}
/*
.CodeMirror-lines {
  padding-left: 0.1em;
}
*/
.CodeMirror-gutters {
  border-right: none;
  width: 1em;
}

time.pending, time.submitted, time.running  {
  color: #cdb62c; /* yellow */
}

time.completed, time.result-ready {
  color: #39aa56; /* green */
}

time.failed, time.signature-mismatch {
  color: #db4545; /* red */
}

time.aborted, time.unknown {
  color: #9d9d9d; /* gray */
}

.task_table a pre, .task_table i {
  color: #666;
}

table.task_table {
  border: 0px;
  border-style: solid;
}

.task_hover {
 color: black !important;
}

/* side panel */
#panel-wrapper #panel .prompt {
 min-width: 0px;
}
#panel-wrapper #panel .output_prompt,
#panel-wrapper #panel .output_prompt_overplay {
 min-width: 0px;
 display: none;
}

#panel-wrapper #panel div.output_area {
  display: -webkit-box;
}

#panel-wrapper #panel div.output_subarea {
  max_width: 100%;
}

#panel-wrapper #panel .output_scroll {
  height: auto;
}

.cm-sos-interpolated {
  background-color: #EDD5F3;
}
.cm-sos-sigil {
  background-color: #EDD5F3;
}
/*
.cm-sos-script {
  font-style: normal;
}

.cm-sos-option {
  font-style: italic;
} */
`;
      document.body.appendChild(css);
    };

    load_css();

    if (Jupyter.notebook.kernel) {
      setup_panel();
    } else {
      events.on("kernel_ready.Kernel", setup_panel);
    }
  }

  function add_panel_button() {
    if (!IPython.toolbar) {
      $([IPython.events]).on("app_initialized.NotebookApp", panel_button);
      return;
    }
    if ($("#panel_button").length === 0) {
      IPython.toolbar.add_buttons_group([{
        "label": "scratch tab",
        "icon": "fa-cube",
        "callback": toggle_panel,
        "id": "panel_button"
      }]);
    }
  };

  /*
  function add_download_menu() {
      if ($("sos_download").length === 0) {
          menu = $("<li id='sos_download'></li>")
              .append($("<a href="#"></a>").html("Report (.html)").onclick(
                  function(){
                      alert("selected");
                  }
              ))
          download_menu = document.getElementById("download_html");
          download_menu.parentNode.insertBefore(menu[0], download_menu.nextSibling);
      }
  }
  */

  function adjustPanel() {
    if ($("#panel-wrapper").css("display") !== "none") {
      var panel_width = nb.metadata["sos"]["panel"].style === "side" ? $("#panel-wrapper").width() : 0;
      $("#notebook-container").css("margin-left", panel_width + 30);
      $("#notebook-container").css("width", $("#site").width() - panel_width - 30);
    }
    var cell = window.my_panel.cell;
    cell.output_area.expand();
  }

  function patch_CodeCell_get_callbacks() {
    var previous_get_callbacks = CodeCell.prototype.get_callbacks;
    CodeCell.prototype.get_callbacks = function() {
      var that = this;
      var callbacks = previous_get_callbacks.apply(this, arguments);
      var prev_reply_callback = callbacks.shell.reply;
      callbacks.shell.reply = function(msg) {
        if (msg.msg_type === "execute_reply") {
          adjustPanel()
        }
        return prev_reply_callback(msg);
      };
      return callbacks;
    };
  }


  function add_lan_selector(cell, kernel) {
    //
    if (cell.element[0].getElementsByClassName("cell_kernel_selector").length > 0) {
      // update existing list
      var select = $(".cell_kernel_selector", cell.element).empty();
      for (var i = 0; i < window.KernelList.length; i++) {
        select.append($("<option/>")
          .attr("value", window.DisplayName[window.KernelList[i][0]])
          .text(window.DisplayName[window.KernelList[i][0]]));
      }
      select.val(kernel ? kernel : "");
      return;
    }
    // add a new one
    var select = $("<select/>").attr("id", "cell_kernel_selector")
      .css("margin-left", "0.75em")
      .attr("class", "select-xs cell_kernel_selector");
    for (var i = 0; i < window.KernelList.length; i++) {
      select.append($("<option/>")
        .attr("value", window.DisplayName[window.KernelList[i][0]])
        .text(window.DisplayName[window.KernelList[i][0]]));
    }
    select.val(kernel ? kernel : "");

    select.change(function() {
      cell.metadata.kernel = window.DisplayName[this.value];
      // cell in panel does not have prompt area
      if (cell.is_panel) {
        if (window.BackgroundColor[this.value])
          cell.element[0].getElementsByClassName("input")[0].style.backgroundColor = window.BackgroundColor[this.value];
        else
          cell.element[0].getElementsByClassName("input")[0].style.backgroundColor = "";
        return;
      }

      var ip = cell.element[0].getElementsByClassName("input_prompt");
      var op = cell.element[0].getElementsByClassName("out_prompt_overlay");
      if (window.BackgroundColor[this.value]) {
        ip[0].style.backgroundColor = window.BackgroundColor[this.value];
        op[0].style.backgroundColor = window.BackgroundColor[this.value];
      } else {
        // Use "" to remove background-color?
        ip[0].style.backgroundColor = "";
        op[0].style.backgroundColor = "";
      }
      // https://github.com/vatlab/sos-notebook/issues/55
      cell.user_highlight = {
        name: 'sos',
        base_mode: window.LanguageName[this.value] || window.KernelName[this.value] || this.value,
      };
      //console.log(`Set cell code mirror mode to ${cell.user_highlight.base_mode}`)
      cell.code_mirror.setOption('mode', cell.user_highlight);
    });

    cell.element.find("div.input_area").prepend(select);
    return select;
  }

  function highlight_cells(cells, i, interval) {
    setTimeout(function() {
      enable_fold_gutter(cells[i]);
      if (cells[i].cell_type === 'code' && cells[i].user_highlight) {
        // console.log(`set ${cells[i].user_highlight} for cell ${i}`);
        cells[i].code_mirror.setOption('mode', cells[i].user_highlight === 'auto' ? 'sos' : cells[i].user_highlight);
      }
      if (i < cells.length)
        highlight_cells(cells, i + 1, interval);
    }, interval);
  }

  var onload = function() {

    // setting up frontend using existing metadata (without executing anything)
    load_select_kernel();
    changeCellStyle();
    // if we reload the page, the cached sos_comm will be removed so we will
    // have to re-register sos_comm. In addition, we will need to notify the
    // kernel that the frontend has been refreshed so that it will create
    // another Comm object. This is done by sending another --list-kernel
    // option.
    if (nb.kernel) {
      // this is needed for refreshing a page...
      register_sos_comm();
      wrap_execute();
    } else {
      events.on("kernel_connected.Kernel", function() {
        register_sos_comm();
        wrap_execute();
      });
    }
    events.on("rendered.MarkdownCell", update_toc);
    events.on("create.Cell", function(evt, param) {
      add_lan_selector(param.cell);
    });
    // I assume that Jupyter would load the notebook before it tries to connect
    // to the kernel, so kernel_connected.kernel is the right time to show toc
    // However, it is possible to load a page without rebooting the kernel so
    // a notebook_load event seems also to be necessary. It is a bit of
    // burden to run show_toc twice but hopefully this provides a more consistent
    // user experience.
    //
    events.on("notebook_loaded.Notebook", show_toc);
    // restart kernel does not clear existing side panel.
    events.on("kernel_connected.Kernel", function() {
      // Issue #1: need to re-register sos_comm after kernel is restarted.
      register_sos_comm();
      var cell = window.my_panel.cell;
      // do not clear existing content
      if (!cell.get_text())
        show_toc()
    });
    // #550
    events.on("select.Cell", set_codemirror_option);
    events.on("select.Cell", highlight_toc_item);

    load_panel();
    add_panel_button();
    // add_download_menu();
    patch_CodeCell_get_callbacks();

    $("#to_markdown").click(function() {
      adjustPanel();
    });
    events.on("kernel_ready.Kernel", function() {
      adjustPanel();
      /* #524. After kernel ready, jupyter would broad cast
       * codemirror mode to all cells, which will overwrite the
       * user mode we have just set. We have no choice but to
       * set codemirror mode again.
       * */
      //nb.set_codemirror_mode("sos");
      highlight_cells(nb.get_cells(), 0, 100);
    });


    // define SOS CodeMirror syntax highlighter
    (function(mod) {
      //if (typeof exports === "object" && typeof module === "object") // CommonJS
      // mod(require("../../lib/codemirror"));
      //else if (typeof define === "function" && define.amd) // AMD
      //  define(["../../lib/codemirror"], mod);
      //else // Plain browser env
      mod(CodeMirror);
    })(function(CodeMirror) {
      "use strict";

      var sosKeywords = ["input", "output", "depends", "parameter"];
      var sosActionWords = ["script", "download", "run", "bash", "sh", "csh",
        "tcsh", "zsh", "python", "python2", "python3", "R", "node", "julia",
        "matlab", "octave", "ruby", "perl", "report", "pandoc", "docker_build",
        "Rmarkdown"
      ];
      var sosMagicWords = ['cd', 'capture', 'clear', 'debug', 'dict', 'expand', 'get',
        'matplotlib', 'paste', 'preview', 'pull', 'push', 'put', 'render',
        'rerun', 'run', 'save', 'sandbox', 'set', 'sessioninfo', 'sosrun',
        'sossave', 'shutdown', 'taskinfo', 'tasks', 'toc', 'use', 'with'
      ]
      var sosFunctionWords = ["sos_run", "logger", "get_output"];

      var hintWords = sosKeywords.concat(sosActionWords).concat(sosFunctionWords)
        .concat(sosMagicWords);

      var sosDirectives = sosKeywords.map(x => x + ":");
      var sosActions = sosActionWords.map(x => x + ":");
      var sosMagics = sosMagicWords.map(x => '%' + x);

      // hint word for SoS mode
      CodeMirror.registerHelper("hintWords", "sos", hintWords);

      var modeMap = {
        'sos': null,
        'python': {
          name: 'python',
          version: 3
        },
        'python2': {
          name: 'python',
          version: 2
        },
        'python3': {
          name: 'python',
          version: 3
        },
        'r': 'r',
        'report': 'markdown',
        'pandoc': 'markdown',
        'download': 'markdown',
        'markdown': 'markdown',
        'ruby': 'ruby',
        'sas': 'sas',
        'bash': 'shell',
        'sh': 'shell',
        'julia': 'julia',
        'run': 'shell',
        'javascript': 'javascript',
        'typescript': {
          name: "javascript",
          typescript: true
        },
        'octave': 'octave',
        'matlab': 'octave',
      }

      function findMode(mode) {
        if (mode in modeMap) {
          return modeMap[mode];
        }
        return null;
      }

      function markExpr(python_mode) {
        return {
          startState: function() {
            return {
              in_python: false,
              sigil: null,
              matched: true,
              python_state: CodeMirror.startState(python_mode),
            };
          },

          copyState: function(state) {
            return {
              in_python: state.in_python,
              sigil: state.sigil,
              matched: state.matched,
              python_state: CodeMirror.copyState(python_mode, state.python_state)
            };
          },

          token: function(stream, state) {
            if (state.in_python) {
              if (stream.match(state.sigil.right)) {
                state.in_python = false;
                state.python_state = CodeMirror.startState(python_mode);
                return "sos-sigil";
              }
              let it = null;
              try {
                it = python_mode.token(stream, state.python_state);
              } catch (error) {
                return "sos-interpolated error" + (state.matched ? "" : " sos-unmatched");
              }
              if (it == 'variable' || it == 'builtin') {
                let ct = stream.current();
                // warn users in the use of input and output in {}
                if (ct === 'input' || ct === 'output')
                  it += ' error';
              }
              return (it ? ("sos-interpolated " + it) : "sos-interpolated") + (state.matched ? "" : " sos-unmatched");
            } else {
              // remove the double brace case, the syntax highlighter
              // does not have to worry (highlight) }}, although it would
              // probably mark an error for single }
              if (state.sigil.left === '{' && stream.match(/\{\{/))
                return null;
              if (stream.match(state.sigil.left)) {
                state.in_python = true;
                // let us see if there is any right sigil till the end of the editor.
                try {
                  let rest = stream.string.slice(stream.pos);
                  if (!rest.includes(state.sigil.right)) {
                    state.matched = false;
                    for (let idx = 1; idx < 5; ++idx) {
                      if (stream.lookAhead(idx).includes(state.sigil.right)) {
                        state.matched = true;
                        break;
                      }
                    }
                  }
                } catch (error) {
                  // only codemirror 5.27.0 supports this function
                }
                return "sos-sigil" + (state.matched ? "" : " sos-unmatched");
              }
              while (stream.next() && !stream.match(state.sigil.left, false)) {}
              return null;
            }
          }
        }
      }

      CodeMirror.defineMode("sos", function(conf, parserConf) {
        let sosPythonConf = {};
        for (let prop in parserConf) {
          if (parserConf.hasOwnProperty(prop)) {
            sosPythonConf[prop] = parserConf[prop];
          }
        }
        sosPythonConf.name = 'python';
        sosPythonConf.version = 3;
        sosPythonConf.extra_keywords = sosActionWords.concat(sosFunctionWords);
        // this is the SoS flavored python mode with more identifiers
        var base_mode = null;
        if ('base_mode' in parserConf && parserConf.base_mode) {
          let mode = findMode(parserConf.base_mode.toLowerCase());
          if (mode) {
            base_mode = CodeMirror.getMode(conf, mode);
          } else {
            console.log(`No base mode is found for ${parserConf.base_mode}. Python mode used.`);
          }
        }
        // if there is a user specified base mode, this is the single cell mode
        if (base_mode) {
          var python_mode = CodeMirror.getMode({}, {
            name: 'python',
            version: 3
          });
          var overlay_mode = markExpr(python_mode);
          return {
            startState: function() {
              return {
                sos_mode: true,
                base_state: CodeMirror.startState(base_mode),
                overlay_state: CodeMirror.startState(overlay_mode),
                // for overlay
                basePos: 0,
                baseCur: null,
                overlayPos: 0,
                overlayCur: null,
                streamSeen: null
              };
            },

            copyState: function(state) {
              return {
                sos_mode: state.sos_mode,
                base_state: CodeMirror.copyState(base_mode, state.base_state),
                overlay_state: CodeMirror.copyState(overlay_mode, state.overlay_state),
                // for overlay
                basePos: state.basePos,
                baseCur: null,
                overlayPos: state.overlayPos,
                overlayCur: null
              };
            },

            token: function(stream, state) {
              if (state.sos_mode) {
                if (stream.sol()) {
                  let sl = stream.peek();
                  if (sl == '!') {
                    stream.skipToEnd();
                    return "meta";
                  } else if (sl == '#') {
                    stream.skipToEnd();
                    return 'comment'
                  }
                  for (var i = 0; i < sosMagics.length; i++) {
                    if (stream.match(sosMagics[i])) {
                      if (sosMagics[i] === "%expand") {
                        // if there is no :, the easy case
                        if (stream.eol() || stream.match(/\s*$/, false)) {
                          state.overlay_state.sigil = {
                            'left': '{',
                            'right': '}'
                          }
                        } else {
                          let found = stream.match(/\s+(\S+)\s+(\S+)$/, false);
                          if (found) {
                            state.overlay_state.sigil = {
                              'left': found[1],
                              'right': found[2]
                            }
                          } else {
                            state.overlay_state.sigil = null;
                          }
                        }
                      }
                      // the rest of the lines will be processed as Python code
                      return "meta";
                    }
                  }
                  state.sos_mode = false;
                } else {
                  stream.skipToEnd();
                  return null;
                }
              }

              if (state.overlay_state.sigil) {
                if (stream != state.streamSeen ||
                  Math.min(state.basePos, state.overlayPos) < stream.start) {
                  state.streamSeen = stream;
                  state.basePos = state.overlayPos = stream.start;
                }

                if (stream.start == state.basePos) {
                  state.baseCur = base_mode.token(stream, state.base_state);
                  state.basePos = stream.pos;
                }
                if (stream.start == state.overlayPos) {
                  stream.pos = stream.start;
                  state.overlayCur = overlay_mode.token(stream, state.overlay_state);
                  state.overlayPos = stream.pos;
                }
                stream.pos = Math.min(state.basePos, state.overlayPos);

                // state.overlay.combineTokens always takes precedence over combine,
                // unless set to null
                return state.overlayCur ? state.overlayCur : state.baseCur;
              } else {
                return base_mode.token(stream, state.base_state);
              }
            },

            indent: function(state, textAfter) {
              // inner indent
              if (!state.sos_mode) {
                if (!base_mode.indent) return CodeMirror.Pass;
                return base_mode.indent(state.base_state, textAfter);
              } else {
                // sos mode has no indent
                return 0;
              }
            },

            innerMode: function(state) {
              return state.sos_mode ? {
                state: state.base_state,
                mode: base_mode
              } : null;
            },

            lineComment: "#",
            fold: "indent"
          };
        } else {
          // this is SoS mode
          base_mode = CodeMirror.getMode(conf, sosPythonConf);
          overlay_mode = markExpr(base_mode);
          return {
            startState: function() {
              return {
                sos_state: null,
                base_state: CodeMirror.startState(base_mode),
                overlay_state: CodeMirror.startState(overlay_mode),
                inner_mode: null,
                inner_state: null,
                // for overlay
                basePos: 0,
                baseCur: null,
                overlayPos: 0,
                overlayCur: null,
                streamSeen: null
              };
            },

            copyState: function(state) {
              return {
                sos_state: state.sos_state,
                base_state: CodeMirror.copyState(base_mode, state.base_state),
                overlay_state: CodeMirror.copyState(overlay_mode, state.overlay_state),
                inner_mode: state.inner_mode,
                inner_state: state.inner_mode && CodeMirror.copyState(state.inner_mode, state.inner_state),
                // for overlay
                basePos: state.basePos,
                baseCur: null,
                overlayPos: state.overlayPos,
                overlayCur: null
              };
            },

            token: function(stream, state) {
              if (stream.sol()) {
                let sl = stream.peek();
                if (sl == '[') {
                  // header, move to the end
                  if (stream.match(/^\[.*\]$/, false)) {
                    // if there is no :, the easy case
                    if (stream.match(/^\[[^:]*\]$/)) {
                      // reset state
                      state.sos_state = null;
                      state.inner_mode = null;
                      return "header";
                    } else {
                      // match up to :
                      stream.match(/^\[[^:]*:/);
                      state.sos_state = 'header_option';
                      return "header";
                    }
                  }
                } else if (sl == '!') {
                  stream.eatWhile(/\S/);
                  return "meta";
                } else if (sl == '%') {
                  stream.eatWhile(/\S/);
                  return "meta";
                } else if (state.sos_state && state.sos_state.startsWith('entering ')) {
                  // the second parameter is starting column
                  let mode = findMode(state.sos_state.slice(9).toLowerCase());
                  state.inner_mode = CodeMirror.getMode({}, mode);
                  state.inner_state = CodeMirror.startState(state.inner_mode, stream.indentation());
                  state.sos_state = null;
                }
                for (var i = 0; i < sosDirectives.length; i++) {
                  if (stream.match(sosDirectives[i])) {
                    // the rest of the lines will be processed as Python code
                    state.sos_state = 'directive_option'
                    return "keyword strong";
                  }
                }
                for (var i = 0; i < sosActions.length; i++) {
                  if (stream.match(sosActions[i])) {
                    // switch to submode?
                    if (stream.eol()) {
                      // really
                      let mode = findMode(stream.current().slice(0, -1).toLowerCase());
                      if (mode) {
                        state.sos_state = "entering " + stream.current().slice(0, -1);
                      } else {
                        state.sos_state = 'unknown_language';
                      }
                    } else {
                      state.sos_state = 'start ' + stream.current().slice(0, -1);
                    }
                    state.overlay_state.sigil = null;
                    return "builtin strong";
                  }
                }
                // if unknown action
                if (stream.match(/\w+:/)) {
                  state.overlay_state.sigil = null;
                  state.sos_state = 'start ' + stream.current().slice(0, -1);
                  return "builtin strong";
                }
              } else if (state.sos_state == 'header_option') {
                // stuff after :
                if (stream.peek() == ']') {
                  // move next
                  stream.next();
                  // ] is the last char
                  if (stream.eol()) {
                    state.sos_state = null;
                    state.inner_mode = null;
                    return "header";
                  } else {
                    stream.backUp(1);
                    let it = base_mode.token(stream, state.base_state);
                    return it ? it + ' sos-option' : null;
                  }
                } else {
                  let it = base_mode.token(stream, state.base_state);
                  return it ? it + ' sos-option' : null;
                }
              } else if (state.sos_state == 'directive_option') {
                // stuff after input:, R: etc
                if (stream.peek() == ',') {
                  // move next
                  stream.next();
                  // , is the last char, continue option line
                  if (stream.eol()) {
                    stream.backUp(1);
                    let it = base_mode.token(stream, state.base_state);
                    return it ? it + ' sos-option' : null;
                  }
                  stream.backUp(1);
                } else if (stream.eol()) {
                  // end of line stops option mode
                  state.sos_state = null;
                  state.inner_mode = null;
                }
                let it = base_mode.token(stream, state.base_state);
                return it ? it + ' sos-option' : null;
              } else if (state.sos_state && state.sos_state.startsWith("start ")) {

                // try to understand option expand=
                if (stream.match(/expand\s*=\s*True/, false)) {
                  // highlight {}
                  state.overlay_state.sigil = {
                    'left': '{',
                    'right': '}'
                  }
                } else {
                  let found = stream.match(/expand\s*=\s*"(\S+) (\S+)"/, false);
                  if (!found)
                    found = stream.match(/expand\s*=\s*'(\S+) (\S+)'/, false);
                  if (found) {
                    state.overlay_state.sigil = {
                      'left': found[1],
                      'right': found[2]
                    }
                  }
                }
                let token = base_mode.token(stream, state.base_state);
                // if it is end of line, ending the starting switch mode
                if (stream.eol() && stream.peek() !== ',') {
                  // really
                  let mode = findMode(state.sos_state.slice(6).toLowerCase());
                  if (mode) {
                    state.sos_state = "entering " + state.sos_state.slice(6);
                  } else {
                    state.sos_state = 'unknown_language';
                  }
                }
                return token + ' sos-option';
              }
              // can be start of line but not special
              if (state.sos_state == 'unknown_language') {
                // we still handle {} in no man unknown_language
                if (state.overlay_state.sigil) {
                  return overlay_mode.token(stream, state.overlay_state);
                } else {
                  stream.skipToEnd();
                  return null;
                }
              } else if (state.inner_mode) {
                let it = 'sos_script ';
                if (!state.overlay_state.sigil) {
                  let st = state.inner_mode.token(stream, state.inner_state);
                  return st ? it + st : null;
                } else {
                  // overlay mode, more complicated
                  if (stream != state.streamSeen ||
                    Math.min(state.basePos, state.overlayPos) < stream.start) {
                    state.streamSeen = stream;
                    state.basePos = state.overlayPos = stream.start;
                  }

                  if (stream.start == state.basePos) {
                    state.baseCur = state.inner_mode.token(stream, state.inner_state);
                    state.basePos = stream.pos;
                  }
                  if (stream.start == state.overlayPos) {
                    stream.pos = stream.start;
                    state.overlayCur = overlay_mode.token(stream, state.overlay_state);
                    state.overlayPos = stream.pos;
                  }
                  stream.pos = Math.min(state.basePos, state.overlayPos);
                  // state.overlay.combineTokens always takes precedence over combine,
                  // unless set to null
                  return (state.overlayCur ? state.overlayCur : state.baseCur) + " sos-script";
                }
              } else {
                return base_mode.token(stream, state.base_state);
              }
            },

            indent: function(state, textAfter) {
              // inner indent
              if (state.inner_mode) {
                if (!state.inner_mode.indent) return CodeMirror.Pass;
                return state.inner_mode.indent(state.inner_mode, textAfter) + 2;
              } else {
                return base_mode.indent(state.base_state, textAfter);
              }
            },

            innerMode: function(state) {
              return state.inner_mode ? null : {
                state: state.base_state,
                mode: base_mode
              };
            },

            lineComment: "#",
            fold: "indent",
            electricInput: /^\s*[\}\]\)]$/,
          };
        };
      }, "python");

      CodeMirror.defineMIME("text/x-sos", "sos");
      // bug vatlab / sos - notebook #55
      CodeMirror.autoLoadMode = function() {};
    });
  }

  return {
    onload: onload
  }
})