/**
 * Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
 * Distributed under the terms of the 3-clause BSD License.
 **/
define([
  "jquery",
  "codemirror/lib/codemirror",
  "codemirror/mode/python/python",
  "codemirror/mode/r/r",
  "codemirror/mode/markdown/markdown",
  "codemirror/addon/selection/active-line",
  "codemirror/addon/fold/foldcode",
  "codemirror/addon/fold/foldgutter",
  "codemirror/addon/fold/indent-fold",
  "codemirror/addon/mode/loadmode"
], function ($) {
  "use strict";
  //variables defined as global which enable access from imported scripts.
  window.BackgroundColor = {};
  window.DisplayName = {};
  window.KernelName = {};
  window.LanguageName = {};
  window.KernelList = [];
  window.JsLoaded = new Map();
  window.KernelOptions = {};
  window.CodeMirrorMode = {};

  window.events = require("base/js/events");
  window.Jupyter = require("base/js/namespace");
  window.CodeCell = require("notebook/js/codecell").CodeCell;

  window.my_panel = null;

  window.sos_comm = null;

  CodeMirror.modeURL = "codemirror/mode/%N/%N";

  var nb = IPython.notebook;

  // initialize BackgroundColor etc from cell meta data
  if (!("sos" in nb.metadata)) {
    nb.metadata["sos"] = {
      kernels: [
        // displayed name, kernel name, language, color
        ["SoS", "sos", "", ""]
      ],
      // panel displayed, position (float or side), old panel height
      panel: {
        displayed: true,
        height: 0
      }
    };
  } else if (!nb.metadata["sos"].panel) {
    nb.metadata["sos"].panel = {
      displayed: true,
      height: 0
    };
  }

  var data = nb.metadata["sos"]["kernels"];
  // upgrade existing meta data if it uses the old 3 item format
  if (
    nb.metadata["sos"]["kernels"].length > 0 &&
    nb.metadata["sos"]["kernels"][0].length === 3
  ) {
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
    window.KernelList.push(data[i][0]);
    // codemirror mode
    if (data[i].length > 4 && data[i][4]) {
      window.CodeMirrorMode[data[i][0]] = data[i][4];
    }
  }

  // if not defined sos version, remove extra kernels saved by
  // sos-notebook 0.9.12.7 or earlier
  if (!nb.metadata["sos"]["version"]) {
    save_kernel_info();
  }

  function load_css(text) {
    var css = document.createElement("style");
    css.type = "text/css";
    css.innerHTML = text;
    document.body.appendChild(css);
  }

  // add language specific css
  function lan_css(lan) {
    if (window.BackgroundColor[lan]) {
      let css_name = safe_css_name(`sos_lan_${lan}`);
      return `.code_cell.${css_name} .input_prompt,
        .${css_name} div.out_prompt_overlay.prompt {
          background: ${window.BackgroundColor[lan]};
          height: 100%;
        }
      `;
    } else {
      return null;
    }
  }

  window.filterDataFrame = function (id) {
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

  window.sortDataFrame = function (id, n, dtype) {
    var table = document.getElementById("dataframe_" + id);

    var tb = table.tBodies[0]; // use `<tbody>` to ignore `<thead>` and `<tfoot>` rows
    var tr = Array.prototype.slice.call(tb.rows, 0); // put rows into array

    var fn =
      dtype === "numeric"
        ? function (a, b) {
          return parseFloat(a.cells[n].textContent) <=
            parseFloat(b.cells[n].textContent)
            ? -1
            : 1;
        }
        : function (a, b) {
          var c = a.cells[n].textContent
            .trim()
            .localeCompare(b.cells[n].textContent.trim());
          return c > 0 ? 1 : c < 0 ? -1 : 0;
        };
    var isSorted = function (array, fn) {
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
    nb.metadata["sos"]["kernels"] = Array.from(used_kernels)
      .sort()
      .map(function (x) {
        return [
          window.DisplayName[x],
          window.KernelName[x],
          window.LanguageName[x] || "",
          window.BackgroundColor[x] || "",
          window.CodeMirrorMode[x] || ""
        ];
      });
    // if some kernel is not registered add them
  }

  function load_kernel_js(kernel_name) {
    let specs = IPython.kernelselector.kernelspecs;
    let ks = specs[kernel_name];
    if (ks && ks.resources["kernel.js"]) {
      console.info(`Dynamically requiring ${ks.resources["kernel.js"]}`);
      requirejs(
        [ks.resources["kernel.js"]],
        function (kernel_mod) {
          if (kernel_mod && kernel_mod.onload) {
            kernel_mod.onload();
          } else {
            console.warn(
              "Kernel " +
              ks.name +
              " has a kernel.js file that does not contain " +
              "any asynchronous module definition. This is undefined behavior " +
              "and not recommended."
            );
          }
        },
        function (err) {
          console.warn(
            "Failed to load kernel.js from ",
            ks.resources["kernel.js"],
            err
          );
        }
      );
    }
    window.JsLoaded.set(kernel_name, true);
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
      } else if (
        lines[l].startsWith("#") ||
        lines[l].startsWith("%") ||
        lines[l].trim() === "" ||
        lines[l].startsWith("!")
      ) {
        continue;
      } else if (lines[l].startsWith("[") && lines[l].endsWith("]")) {
        // include comments before section header
        let c = l - 1;
        let comment = "";
        while (c >= 0 && lines[c].startsWith("#")) {
          comment = lines[c] + "\n" + comment;
          c -= 1;
        }
        workflow += comment + lines.slice(l).join("\n") + "\n\n";
        break;
      }
    }
    return workflow;
  }

  // get workflow from notebook
  function getNotebookWorkflow(cells) {
    let workflow = "";

    for (let i = 0; i < cells.length; ++i) {
      let cell = cells[i];
      if (
        cell.cell_type === "code" &&
        (!cell.metadata["kernel"] || cell.metadata["kernel"] === "SoS")
      ) {
        workflow += getCellWorkflow(cell);
      }
    }
    if (workflow != "") {
      workflow = "#!/usr/bin/env sos-runner\n#fileformat=SOS1.0\n\n" + workflow;
    }
    return workflow;
  }

  function getNotebookContent(cells) {
    let workflow = "#!/usr/bin/env sos-runner\n#fileformat=SOS1.0\n\n";

    for (let i = 0; i < cells.length; ++i) {
      let cell = cells[i];
      if (cell.cell_type === "code") {
        workflow += `# cell ${i + 1}, kernel=${cell.metadata["kernel"]}\n${cell.get_text()}\n\n`
      }
    }
    return workflow;
  }


  var my_execute = function (code, callbacks, options) {
    /* check if the code is a workflow call, which is marked by
     * %sosrun or %sossave workflowname with options
     */
    options.sos = {};
    var run_notebook = code.match(
      /^%sosrun($|\s)|^%convert($|\s)|^%preview\s.*(-w|--workflow).*$/m
    );

    var cells = nb.get_cells();
    if (run_notebook) {
      // Running %sossave --to html needs to save notebook
      nb.save_notebook();
      if (code.match(
        /^%convert\s.*(-a|--all).*$/m
      )) {
        options.sos.workflow = getNotebookContent(cells);
      } else {
        options.sos.workflow = getNotebookWorkflow(cells);
      }
    }
    options.sos.path = nb.notebook_path;
    options.sos.use_panel = nb.metadata["sos"]["panel"].displayed;
    for (var i = cells.length - 1; i >= 0; --i) {
      // this is the cell that is being executed...
      // according to this.set_input_prompt("*") before execute is called.
      // also, because a cell might be starting without a previous cell
      // being finished, we should start from reverse and check actual code
      if (
        cells[i].input_prompt_number === "*" &&
        code === cells[i].get_text()
      ) {
        options.sos.cell_id = cells[i].cell_id;
        options.sos.cell_kernel = cells[i].metadata.kernel;
        return this.orig_execute(code, callbacks, options);
      }
    }
    options.sos.cell_kernel = window.my_panel.cell.metadata.kernel;
    options.sos.cell_id = "0";
    options.silent = false;
    options.store_history = true;
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
        fileref.onload = function () {
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
    if (id && id != "0") {
      return nb.get_cells().find(cell => cell.cell_id === id);
    } else {
      return window.my_panel.cell;
    }
  }

  function get_cell_by_elem(elem) {
    return nb.get_cells().find(cell => cell.element[0] === elem);
  }

  function changeStyleOnKernel(cell) {
    var type = cell.cell_type === "code" ? cell.metadata.kernel : "";
    // type should be  displayed name of kernel
    var sel = cell.element[0].getElementsByClassName("cell_kernel_selector")[0];
    if (!type) {
      sel.selectedIndex = -1;
    } else {
      var opts = sel.options;
      var opt, j;
      for (j = 0; (opt = opts[j]); j++) {
        if (opt.value === window.DisplayName[type]) {
          sel.selectedIndex = j;
          break;
        }
      }
    }

    if (
      cell.metadata.tags &&
      cell.metadata.tags.indexOf("report_output") >= 0
    ) {
      $(".output_wrapper", cell.element).addClass("report_output");
    } else {
      $(".output_wrapper", cell.element).removeClass("report_output");
    }
    $(cell.element)
      .removeClass((index, className) => {
        return (className.match(/(^|\s)sos_lan_\S+/g) || []).join(" ");
      })
      .addClass(safe_css_name(`sos_lan_${type}`));
    // cell in panel does not have prompt area
    if (cell.is_panel) {
      cell.user_highlight = {
        name: "sos",
        base_mode: window.CodeMirrorMode[type] ||
          window.LanguageName[type] ||
          window.KernelName[type] ||
          type
      };
      //console.log(`Set cell code mirror mode to ${cell.user_highlight}`)
      cell.code_mirror.setOption("mode", cell.user_highlight);
      return;
    }

    if (type) {
      let kernel_name = window.KernelName[type];
      if (kernel_name !== "sos" && !window.JsLoaded[kernel_name]) {
        load_kernel_js(kernel_name);
      }
      var base_mode =
        window.CodeMirrorMode[type] ||
        window.LanguageName[type] ||
        kernel_name ||
        type;
      if (!base_mode || base_mode === "sos") {
        cell.user_highlight = "auto";
        cell.code_mirror.setOption("mode", "sos");
      } else {
        cell.user_highlight = {
          name: "sos",
          base_mode: base_mode
        };
        cell.code_mirror.setOption("mode", cell.user_highlight);
      }
    }
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
      // selector is added to all cells but will not be Displayed
      // for non-code cell
      add_lan_selector(cells[i]);
      if (cells[i].cell_type === "code") {
        changeStyleOnKernel(cells[i]);
      }
    }
    if (window.my_panel) {
      add_lan_selector(window.my_panel.cell);
      changeStyleOnKernel(window.my_panel.cell);
    }

    let css_text = window.KernelList.map(lan_css)
      .filter(Boolean)
      .join("\n");
    load_css(css_text);
  }

  function update_duration() {
    if (window._duration_updater) return;
    window._duration_updater = window.setInterval(function () {
      document.querySelectorAll("[id^='status_duration_']").forEach(item => {
        if (item.className != "running") {
          return;
        }
        item.innerText =
          "Ran for " +
          window.durationFormatter(new Date() - item.getAttribute("datetime"));
      });
    }, 5000);
  }

  /* When a notebook is opened with multiple workflow or task tables,
   * the tables have display_id but the ID maps will not be properly
   * setup so that the tables cannot be updated with another
   * update_display_data message. To fix this problem, we will have
   * to manually populate the
   *   output_area._display_id_targets
   * structure.
   */
  function isEmpty(map) {
    for (var key in map) {
      if (map.hasOwnProperty(key)) {
        return false;
      }
    }
    return true;
  }

  function fix_display_id(cell) {
    if (!isEmpty(cell.output_area._display_id_targets)) {
      return;
    }
    for (let idx = 0; idx < cell.output_area.outputs.length; ++idx) {
      let output = cell.output_area.outputs[idx];
      if (output.output_type != "display_data" || !output.data["text/html"]) {
        continue;
      }
      if (!output.data || !output.data["text/html"]) {
        continue;
      }
      // the HTML should look like
      // <table id="task_macpro_90775d4e30583c18" class="task_table running">
      let id = output.data["text/html"].match(/id="([^"]*)"/);
      if (!id || !id[1]) {
        continue;
      }
      let target_id = id[1];
      if (target_id.match('^task_.*')) {
        target_id = target_id.split("_").slice(0, -1).join("_");
      }
      let targets = cell.output_area._display_id_targets[target_id];
      if (!targets) {
        targets = cell.output_area._display_id_targets[target_id] = [];
      }
      targets.push({
        index: idx,
        element: $(document.getElementById(id[1]).parentNode.parentNode)
      });
    }
  }

  // add workflow status indicator table
  function update_workflow_status(info) {
    // find the cell
    let cell_id = info.cell_id;
    let cell = get_cell_by_id(cell_id);
    if (!cell) {
      console.log(`Cannot find cell by ID ${info.cell_id}`);
      return;
    }

    // if there is an existing status table, try to retrieve its information
    // if the new data does not have it
    let has_status_table = document.getElementById(`workflow_${cell_id}`);
    if (!has_status_table && info.status != "pending") {
      return;
    }
    let timer_text = "";
    if (info.start_time) {
      // convert from python time to JS time.
      info.start_time = info.start_time * 1000;
    }
    if (info.status == "purged") {
      if (!has_status_table) {
        return;
      }
      let data = {
        output_type: "update_display_data",
        transient: { display_id: `workflow_${cell_id}` },
        metadata: {},
        data: {
          "text/html": ""
        }
      };
      fix_display_id(cell);
      cell.output_area.append_output(data);
    }
    if (has_status_table) {
      // if we already have timer, let us try to "fix" it in the notebook
      let timer = document.getElementById(`status_duration_${cell_id}`);
      timer_text = timer.innerText;
      if (
        timer_text === "" &&
        (info.status === "completed" ||
          info.status === "failed" ||
          info.status === "aborted")
      ) {
        timer_text = "Ran for < 5 seconds";
      }
      if (!info.start_time) {
        info.start_time = timer.getAttribute("datetime");
      }
      //
      if (!info.workflow_id) {
        info.workflow_id = document.getElementById(
          `workflow_id_${cell_id}`
        ).innerText;
      }
      if (!info.workflow_name) {
        info.workflow_name = document.getElementById(
          `workflow_name_${cell_id}`
        ).innerText;
      }
      if (!info.index) {
        info.index = document.getElementById(
          `workflow_index_${cell_id}`
        ).innerText;
      }
    }
    // new and existing, check icon
    let status_class = {
      pending: "fa-square-o",
      running: "fa-spinner fa-pulse fa-spin",
      completed: "fa-check-square-o",
      failed: "fa-times-circle-o",
      aborted: "fa-frown-o"
    };

    // look for status etc and update them.
    let onmouseover = `onmouseover='this.classList="fa fa-2x fa-fw fa-trash"'`;
    let onmouseleave = `onmouseleave='this.classList="fa fa-2x fa-fw ${status_class[info.status]}"'`;
    let onclick = `onclick="cancel_workflow(this.id.substring(21))"`;

    let data = {
      output_type: has_status_table ? "update_display_data" : "display_data",
      transient: { display_id: `workflow_${cell_id}` },
      metadata: {},
      data: {
        "text/html": `
<table id="workflow_${cell_id}" class="workflow_table  ${info.status}">
  <tr>
        <td class="workflow_icon">
          <i id="workflow_status_icon_${cell_id}" class="fa fa-2x fa-fw ${status_class[info.status]}"
          ${onmouseover} ${onmouseleave} ${onclick}></i>
        </td>
        <td class="workflow_name">
          <pre><span id="workflow_name_${cell_id}">${info.workflow_name}</span></pre>
        </td>
        <td class="workflow_id">
          <span>Workflow ID</span></br>
          <pre><i class="fa fa-fw fa-sitemap"></i><span id="workflow_id_${cell_id}">${info.workflow_id}</span></pre>
        </td>
        <td class="workflow_index">
          <span>Index</span></br>
          <pre>#<span id="workflow_index_${cell_id}">${info.index}</span></pre>
        </td>
        <td class="workflow_status">
          <span id="status_text_${cell_id}">${info.status}</span></br>
          <pre><i class="fa fa-fw fa-clock-o"></i><time id="status_duration_${cell_id}" class="${info.status}" datetime="${info.start_time}">${timer_text}</time></pre>
        </td>
  </tr>
</table>
`
      }
    };
    // find the status table
    cell.output_area.append_output(data);
  }

  function update_task_status(info) {
    // find the cell
    //console.log(info);
    // special case, purge by tag, there is no task_id
    if (!info.task_id && info.tag && info.status == "purged") {
      // find all elements by tag
      let elems = document.getElementsByClassName(`task_tag_${info.tag}`);
      if (!elems) {
        return;
      }
      let cell_elems = Array.from(elems).map(x => x.closest(".code_cell"));
      let cells = cell_elems.map(cell_elem => get_cell_by_elem(cell_elem));
      let display_ids = Array.from(elems).map(x =>
        x
          .closest(".task_table")
          .id.split("_")
          .slice(0, -1)
          .join("_")
      );

      for (let i = 0; i < cells.length; ++i) {
        let data = {
          output_type: "update_display_data",
          transient: { display_id: display_ids[i] },
          metadata: {},
          data: {
            "text/html": ""
          }
        };
        fix_display_id(cells[i]);
        cells[i].output_area.append_output(data);
      }
      return;
    }

    let elem_id = `${info.queue}_${info.task_id}`;
    // convert between Python and JS float time
    if (info.start_time) {
      info.start_time = info.start_time * 1000;
    }
    // find the status table
    let cell_id = info.cell_id;
    let cell = null;
    let has_status_table = false;
    if (cell_id) {
      cell = get_cell_by_id(cell_id);
      has_status_table = document.getElementById(`task_${elem_id}_${cell_id}`);
      if (!has_status_table && info.status !== 'pending') {
        // if there is already a table inside, with cell_id that is different from before...
        has_status_table = document.querySelector(
          `[id^="task_${elem_id}"]`
        );
        if (has_status_table) {
          cell_id = has_status_table.id.split("_").slice(-1)[0];
          cell = get_cell_by_id(cell_id);
        }
      }
      if (info.update_only && !has_status_table) {
        console.log(
          `Cannot find cell by cell ID ${info.cell_id} or task ID ${info.task_id} to update`
        );
        return;
      }
    } else {
      // note that there might be multiple task table that matches this task_id
      has_status_table = document.querySelector(`[id^="task_${elem_id}"]`);
      cell = get_cell_by_elem(has_status_table.closest(".code_cell"));
      cell_id = cell.cell_id;
    }
    if (cell) {
      fix_display_id(cell);
    } else {
      console.log(
        `Cannot find cell by cell ID ${info.cell_id} or task ID ${info.task_id}`
      );
      return;
    }
    if (info.status == "purged") {
      if (has_status_table) {
        let data = {
          output_type: "update_display_data",
          transient: { display_id: `task_${elem_id}` },
          metadata: {},
          data: {
            "text/html": ""
          }
        };
        cell.output_area.append_output(data);
      }
      return;
    }
    // if there is an existing status table, try to retrieve its information
    // the new data does not have it
    let timer_text = "";
    if (has_status_table) {
      // if we already have timer, let us try to "fix" it in the notebook
      let timer = document.querySelector(`[id^="status_duration_${elem_id}"]`);
      timer_text = timer.innerText;
      if (
        timer_text === "" &&
        (info.status === "completed" ||
          info.status === "failed" ||
          info.status === "aborted")
      ) {
        timer_text = "Ran for < 5 seconds";
      }
      if (!info.start_time) {
        info.start_time = timer.getAttribute("datetime");
      }
      if (!info.tags) {
        info.tags = document.querySelector(
          `[id^="status_tags_${elem_id}"]`
        ).innerText;
      }
    }

    let status_class = {
      pending: "fa-square-o",
      submitted: "fa-spinner",
      running: "fa-spinner fa-pulse fa-spin",
      completed: "fa-check-square-o",
      failed: "fa-times-circle-o",
      aborted: "fa-frown-o",
      missing: "fa-question"
    };

    // look for status etc and update them.
    let id_elems =
      `<pre>${info.task_id}` +
      `<div class="task_id_actions">` +
      `<i class="fa fa-fw fa-refresh" onclick="task_action({action:'status', task:'${info.task_id}', queue: '${info.queue}'})"></i>` +
      `<i class="fa fa-fw fa-play" onclick="task_action({action:'execute', task:'${info.task_id}', queue: '${info.queue}'})"></i>` +
      `<i class="fa fa-fw fa-stop"" onclick="task_action({action:'kill', task:'${info.task_id}', queue: '${info.queue}'})"></i>` +
      `<i class="fa fa-fw fa-trash"" onclick="task_action({action:'purge', task:'${info.task_id}', queue: '${info.queue}'})"></i>` +
      `</div></pre>`;

    let tags = info.tags.split(/\s+/g);
    let tags_elems = "";
    for (let ti = 0; ti < tags.length; ++ti) {
      let tag = tags[ti];
      if (!tag) {
        continue;
      }
      tags_elems +=
        `<pre class="task_tags task_tag_${tag}">${tag}` +
        `<div class="task_tag_actions">` +
        `<i class="fa fa-fw fa-refresh" onclick="task_action({action:'status', tag:'${tag}', queue: '${info.queue}'})"></i>` +
        `<i class="fa fa-fw fa-stop"" onclick="task_action({action:'kill', tag:'${tag}', queue: '${info.queue}'})"></i>` +
        `<i class="fa fa-fw fa-trash"" onclick="task_action({action:'purge', tag:'${tag}', queue: '${info.queue}'})"></i>` +
        `</div></pre>`;
    }

    let data = {
      output_type: has_status_table ? "update_display_data" : "display_data",
      transient: { display_id: `task_${elem_id}` },
      metadata: {},
      data: {
        "text/html": `
<table id="task_${elem_id}_${cell_id}" class="task_table ${info.status}">
<tr>
    <td class="task_icon">
      <i id="task_status_icon_${elem_id}_${cell_id}" class="fa fa-2x fa-fw ${status_class[info.status]}"</i>
    </td>
  <td class="task_id">
      <span><pre><i class="fa fa-fw fa-sitemap"></i></pre>${id_elems}</span>
    </td>
    <td class="task_tags">
      <span id="status_tags_${elem_id}_${cell_id}"><pre><i class="fa fa-fw fa-info-circle"></i></pre>${tags_elems}</span>
    </td>
    <td class="task_timer">
      <pre><i class="fa fa-fw fa-clock-o"></i><time id="status_duration_${elem_id}_${cell_id}" class="${info.status}" datetime="${info.start_time}">${timer_text}</time></pre>
    </td>
    <td class="task_status">
      <pre><i class="fa fa-fw fa-tasks"></i><span id="status_text_${elem_id}_${cell_id}">${info.status}</span></pre>
    </td>
</tr>
</table>
`
      }
    };
    cell.output_area.append_output(data);
  }

  function register_sos_comm() {
    // comm message sent from the kernel
    window.sos_comm = Jupyter.notebook.kernel.comm_manager.new_comm(
      "sos_comm",
      {}
    );
    window.sos_comm.on_msg(function (msg) {
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
          if (window.KernelList.findIndex(item => item === data[i][0]) === -1) {
            window.KernelList.push(data[i][0]);
          }
          // if codemirror mode ...
          if (data[i].length > 4 && data[i][4]) {
            window.CodeMirrorMode[data[i][0]] = data[i][4];
          }
          // if options ...
          if (data[i].length > 5) {
            window.KernelOptions[data[i][0]] = data[i][5];
          }

          // if the kernel is in metadata, check conflict
          k_idx = nb.metadata["sos"]["kernels"].findIndex(
            item => item[0] === data[i][0]
          );
          if (k_idx !== -1) {
            var r;
            // if kernel exist update the rest of the information, but warn users first on
            // inconsistency
            if (
              nb.metadata["sos"]["kernels"][k_idx][1] !== data[i][1] &&
              nb.metadata["sos"]["kernels"][k_idx][1]
            ) {
              // r = confirm(
              //   "This notebook used Jupyter kernel " +
              //   nb.metadata["sos"]["kernels"][k_idx][1] +
              //   " for subkernel " +
              //   data[i][0] +
              //   ". Do you want to switch to " +
              //   data[i][1] +
              //   " instead?"
              // );
              // if (!r) {
              window.KernelName[data[i][0]] =
                nb.metadata["sos"]["kernels"][k_idx][1];
              // }
            }
            if (
              nb.metadata["sos"]["kernels"][k_idx][2] !== data[i][2] &&
              nb.metadata["sos"]["kernels"][k_idx][2]
            ) {
              if (data[i][2] !== "") {
                r = confirm(
                  "This notebook used language definition " +
                  nb.metadata["sos"]["kernels"][k_idx][2] +
                  " for subkernel " +
                  data[i][0] +
                  ". Do you want to switch to " +
                  data[i][2] +
                  " instead?"
                );
                if (!r) {
                  window.LanguageName[data[i]][0] =
                    nb.metadata["sos"]["kernels"][k_idx][2];
                }
              }
            }
          }
        }
        //add dropdown menu of kernels in frontend
        load_select_kernel();
        console.log("kernel list updated");
      } else if (msg_type === "cell-kernel") {
        // get cell from passed cell index, which was sent through the
        // %frontend magic

        cell = get_cell_by_id(data[0]);

        if (cell.metadata.kernel !== window.DisplayName[data[1]]) {
          cell.metadata.kernel = window.DisplayName[data[1]];
          // set meta information
          changeStyleOnKernel(cell);
          save_kernel_info();

          let cellIndex = nb.find_cell_index(cell);
          let nextCell = nb.get_cell(cellIndex + 1);

          if (
            nextCell !== null &&
            cellIndex + 2 === nb.get_cells().length &&
            nextCell.get_text() === ""
          ) {
            nextCell.metadata.kernel = cell.metadata.kernel;
            changeStyleOnKernel(nextCell);
          }
        } else if (
          cell.metadata.tags &&
          cell.metadata.tags.indexOf("report_output") >= 0
        ) {
          // #639
          // if kernel is different, changeStyleOnKernel would set report_output.
          // otherwise we mark report_output
          $(".output_wrapper", cell.element).addClass("report_output");
        }
      } else if (msg_type === "preview-kernel") {
        window.my_panel.cell.metadata.kernel = data;
        changeStyleOnKernel(window.my_panel.cell);
      } else if (msg_type === "highlight-workflow") {
        let elem = document.getElementById(data[1]);
        CodeMirror.fromTextArea(elem, {
          mode: "sos"
        });
        // if in a regular notebook, we use static version of the HTML
        // to replace the codemirror js version.
        if (data[0]) {
          let cell = get_cell_by_id(data[0]);
          let cm_node = elem.parentElement.lastElementChild;
          cell.output_area.append_output({
            output_type: "update_display_data",
            transient: { display_id: data[1] },
            metadata: {},
            data: {
              "text/html": cm_node.outerHTML
            }
          });
          cm_node.remove();
        }
      } else if (msg_type === "remove-task") {
        var item = document.querySelector(
          `[id^="table_${data[0]}_${data[1]}"]`
        );
        if (item) {
          item.parentNode.removeChild(item);
        }
      } else if (msg_type === "update-duration") {
        update_duration();
      } else if (msg_type === "task_status") {
        update_task_status(data);
        if (data.status === "running") {
          update_duration();
        }
      } else if (msg_type == "print") {
        cell = get_cell_by_id(data[0]);
        cell.output_area.append_output({
          output_type: "stream",
          name: "stdout",
          text: data[1]
        });
      } else if (msg_type == "workflow_status") {
        update_workflow_status(data);
        if (data.status === "running") {
          update_duration();
        }
        // if this is a terminal status, try to execute the
        // next pending workflow
        if (
          data.status === "completed" ||
          data.status === "canceled" ||
          data.status === "failed"
        ) {
          // find all cell_ids with pending workflows
          let elems = document.querySelectorAll("[id^='status_duration_']");
          let pending = Array.from(elems)
            .filter(item => {
              return (
                item.className == "pending" &&
                !item.id.substring(16).includes("_")
              );
            })
            .map(item => {
              return item.id.substring(16);
            });
          if (pending) {
            execute_workflow(pending);
          }
        }
      } else if (msg_type === "paste-table") {
        var cm = nb.get_selected_cell().code_mirror;
        cm.replaceRange(data, cm.getCursor());
      } else if (msg_type === "alert") {
        alert(data);
      } else if (msg_type === "notebook-version") {
        // right now no upgrade, just save version to notebook
        nb.metadata["sos"]["version"] = data;
      } else if (msg_type === "transient_display_data") {
        cell = create_panel_cell("");
        // append the output
        data.output_type = "display_data";
        cell.output_area.append_output(data);
        scrollPanel();
      } else {
        // this is preview output
        cell = create_panel_cell("");
        data.output_type = msg_type;
        last_cell.output_area.append_output(data);
        scrollPanel();
      }
    });

    window.sos_comm.send({
      "list-kernel": nb.metadata["sos"]["kernels"],
      "update-task-status": window.unknown_tasks,
      "notebook-version": nb.metadata["sos"]["version"] || "undefined"
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

  window.cancel_workflow = function (cell_id) {
    console.log("Cancel workflow " + cell_id);
    send_kernel_msg({
      "cancel-workflow": [cell_id]
    });
  };

  window.execute_workflow = function (cell_ids) {
    console.log("Run workflows " + cell_ids);
    send_kernel_msg({
      "execute-workflow": cell_ids
    });
  };

  window.task_action = function (param) {
    if (!param.action) {
      return;
    }
    create_panel_cell(
      `%task ${param.action}` +
      (param.task ? ` ${param.task}` : "") +
      (param.tag ? ` -t ${param.tag}` : "") +
      (param.queue ? ` -q ${param.queue}` : "")
    ).execute();
    scrollPanel();
  };

  window.durationFormatter = function (ms) {
    var res = [];
    var seconds = parseInt(ms / 1000);
    var day = Math.floor(seconds / 86400);
    if (day > 0) {
      res.push(day + " day" + (day > 1 ? "s" : ""));
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

  function changeCellStyle() {
    var cells = nb.get_cells();
    // setting up background color and selection according to notebook metadata
    var i;
    for (i in cells) {
      if (cells[i].cell_type === "code") {
        changeStyleOnKernel(cells[i]);
      }
    }
    $("[id^=task_status_]")
      .removeAttr("onClick")
      .removeAttr("onmouseover")
      .removeAttr("onmouseleave");
    var tasks = $("[id^=task_status_]");
    window.unknown_tasks = [];
    for (i = 0; i < tasks.length; ++i) {
      // status_localhost_5ea9232779ca1959
      if (tasks[i].id.match("^task_status_icon_.+$")) {
        tasks[i].className = "fa fa-fw fa-2x fa-refresh fa-spin";
        window.unknown_tasks.push(tasks[i].id.substring(17));
      }
    }
  }

  function notify_cell_kernel(evt, param) {
    var cell = param.cell;
    if (cell.cell_type === "code") {
      send_kernel_msg({
        "set-editor-kernel": cell.metadata.kernel
      });
    }
  }

  function incr_lbl(ary, h_idx) {
    //increment heading label  w/ h_idx (zero based)
    ary[h_idx]++;
    for (var j = h_idx + 1; j < ary.length; j++) {
      ary[j] = 0;
    }
    return ary.slice(0, h_idx + 1);
  }

  function removeMathJaxPreview(elt) {
    elt.find("script[type='math/tex']").each(function (i, e) {
      $(e).replaceWith("$" + $(e).text() + "$");
    });
    elt.find("span.MathJax_Preview").remove();
    elt.find("span.MathJax").remove();
    return elt;
  }



  var create_panel_div = function () {
    var panel_wrapper = $("<div id='panel-wrapper'/>").append(
      $("<div/>")
        .attr("id", "panel")
        .addClass("panel")
    );

    $("body").append(panel_wrapper);
    $("#notebook-container").addClass("without_console_panel");

    $([Jupyter.events]).on("resize-header.Page", function () {
      $("#panel-wrapper").css("top", $("#header").height());
      $("#panel-wrapper").css("height", $("#site").height());
    });
    $([Jupyter.events]).on("toggle-all-headers", function () {
      var headerVisibleHeight = $("#header").is(":visible")
        ? $("#header").height()
        : 0;
      $("#panel-wrapper").css("top", headerVisibleHeight);
      $("#panel-wrapper").css("height", $("#site").height());
    });

    $(".output_scroll").on("resizeOutput", function () {
      var output = $(this);
      setTimeout(function () {
        output.scrollTop(output.prop("scrollHeight"));
      }, 0);
    });

    // enable dragging and save position on stop moving
    $("#panel-wrapper").draggable({ disabled: true });

    $("#panel-wrapper").resizable({
      resize: function (event, ui) {
        $("#notebook-container").css(
          "margin-left",
          $("#panel-wrapper").width() + 25
        );
        $("#notebook-container").css(
          "width",
          $("#notebook").width() - $("#panel-wrapper").width() - 40
        );
      },
      start: function (event, ui) {
        $(this).width($(this).width());
        //$(this).css("position", "fixed");
      }
    });

    $("#site").bind("siteHeight", function () {
      $("#panel-wrapper").css("height", $("#site").height());
    });

    $("#site").trigger("siteHeight");

    $("#panel-wrapper").addClass("sidebar-wrapper");

    $(window).resize(function () {
      if ($("#panel-wrapper").css("display") !== "flex") {
        return;
      }
      $("#panel").css({
        maxHeight: $(window).height() - 30
      });
      $("#panel-wrapper").css({
        maxHeight: $(window).height() - 10
      });

      if ($("#panel-wrapper").css("display") === "flex") {
        $("#notebook-container").css(
          "margin-left",
          $("#panel-wrapper").width() + 25
        );
        $("#notebook-container").css(
          "width",
          $("#notebook").width() - $("#panel-wrapper").width() - 40
        );
        $("#panel-wrapper").css("height", $("#site").height());
        $("#panel-wrapper").css("top", $("#header").height());
      }
    });
    $(window).trigger("resize");
  };

  function create_panel_cell(text, kernel = "SoS") {
    if (!text && window.last_panel_output_cell) {
      return window.last_panel_output_cell;
    }

    // create my cell
    var cell = new CodeCell(nb.kernel, {
      events: nb.events,
      config: nb.config,
      keyboard_manager: nb.keyboard_manager,
      notebook: nb,
      tooltip: nb.tooltip
    });
    cell.element.addClass(text ? "console-cell" : "console-output-cell");
    cell.metadata.kernel = kernel;
    cell.metadata.editable = false;
    if (text) {
      add_lan_selector(cell).prop("disabled", true);
      cell.set_input_prompt();
      cell.set_text(text);

      changeStyleOnKernel(cell);
    }

    // remove cell toolbar
    $(".celltoolbar", cell.element).remove();
    $(".ctb_hideshow", cell.element).remove();
    cell.element[0].style.fontSize = "90%";

    $("#panel").append(cell.element);
    cell.render();
    cell.refresh();

    window.last_panel_output_cell = text ? null : cell;
    return cell;
  }

  function scrollPanel() {
    let panel = document.getElementById("panel");
    $(panel).animate(
      {
        scrollTop: panel.scrollHeight - panel.clientHeight
      },
      100
    );
  }

  var panel = function (nb) {
    var panel = this;
    this.notebook = nb;
    this.kernel = nb.kernel;
    this.km = nb.keyboard_manager;
    // for history navigation
    this.cell_input = "";
    this.history_index = 0;

    create_panel_div();
    console.log("panel created");

    // create my cell
    var cell = (this.cell = new CodeCell(nb.kernel, {
      events: nb.events,
      config: nb.config,
      keyboard_manager: nb.keyboard_manager,
      notebook: nb,
      tooltip: nb.tooltip
    }));
    cell.metadata.kernel = "SoS";
    add_lan_selector(cell);
    add_panel_icons(cell);
    cell.set_input_prompt();
    $(".output_wrapper", cell.element).remove();

    cell.is_panel = true;
    $("#panel-wrapper").append(this.cell.element);

    cell.render();
    cell.refresh();
    this.cell.element.addClass("anchor-cell");

    // remove cell toolbar
    $(".celltoolbar", cell.element).remove();
    $(".ctb_hideshow", cell.element).remove();
    //this.cell.element.find("code_cell").css("position", "absolute").css("top", "1.5em");
    this.cell.element
      .find("div.input_prompt")
      .addClass("panel_input_prompt")
      .text("[ ]:");
    // this.cell.element.find("div.input_area").css("margin-top", "20pt");

    // make the font of the panel slightly smaller than the main notebook
    // unfortunately the code mirror input cell has fixed font size that cannot
    // be changed.
    this.cell.element[0].style.fontSize = "90%";
    console.log("panel rendered");

    // override ctrl/shift-enter to execute me if I'm focused instead of the notebook's cell
    var execute_and_select_action = this.km.actions.register(
      {
        handler: $.proxy(this.execute_and_select_event, this)
      },
      "panel-execute-and-select"
    );
    var execute_action = this.km.actions.register(
      {
        handler: $.proxy(this.execute_event, this)
      },
      "panel-execute"
    );
    var toggle_action = this.km.actions.register(
      {
        handler: $.proxy(toggle_panel, this)
      },
      "panel-toggle"
    );

    var run_in_console_action = this.km.actions.register(
      {
        help: "run selected text in panel cell",
        handler: run_in_console
      },
      "run-in-console",
      "sos"
    );
    var paste_table = this.km.actions.register(
      {
        help: "paste table as markdown",
        handler: paste_table_as_markdown
      },
      "paste-table"
    );
    var toggle_output = this.km.actions.register(
      {
        help: "toggle display output in HTML",
        handler: toggle_display_output
      },
      "toggle-show-output"
    );
    var toggle_kernel = this.km.actions.register(
      {
        help: "toggle cell kernel",
        handler: toggle_cell_kernel
      },
      "toggle-show-output"
    );
    var toggle_markdown = this.km.actions.register(
      {
        help: "toggle between markdown and code cells",
        handler: toggle_markdown_cell
      },
      "toggle-markdown"
    );
    var up_arrow = this.km.actions.register(
      {
        help: "move cursor to previous line or cell",
        handler: $.proxy(this.move_cursor_up, this)
      },
      "move-cursor-up"
    );
    var down_arrow = this.km.actions.register(
      {
        help: "move cursor to next line or cell",
        handler: $.proxy(this.move_cursor_down, this)
      },
      "move-cursor-down"
    );
    var shortcuts = {
      "shift-enter": execute_and_select_action,
      "ctrl-enter": execute_action,
      "ctrl-b": toggle_action,
      // It is very strange to me that other key bindings such as
      // Ctrl-e does not work as it will somehow make the
      // code_mirror.getSelection() line getting only blank string.
      "ctrl-shift-enter": run_in_console_action,
      "ctrl-shift-o": toggle_output,
      "ctrl-shift-s": toggle_kernel,
      "ctrl-shift-v": paste_table,
      "ctrl-shift-m": toggle_markdown,
      up: up_arrow,
      down: down_arrow
    };
    this.km.edit_shortcuts.add_shortcuts(shortcuts);
    this.km.command_shortcuts.add_shortcuts(shortcuts);

    create_panel_cell("").output_area.append_output({
      output_type: "display_data",
      data: {
        "text/plain":
          'Execute commands in the scratch cell below or use shortcut "Ctrl-Shift-Enter" to execute current line or selected text of cells here.',
        "text/html":
          "Execute commands in the scratch cell below or use shortcut <code>Ctrl-Shift-Enter</code> to execute current line or selected text of cells here."
      }
    });

    this.cell.element.show();
    this.cell.focus_editor();
  };

  panel.prototype.execute_and_select_event = function (evt) {
    // if we execute statements before the kernel is wrapped
    // from other channels (update kernel list etc), wrap it now.
    wrap_execute();

    if (this.cell.element[0].contains(document.activeElement)) {
      let text = this.cell.get_text();
      if (text.trim() === "clear") {
        $("#panel")
          .children()
          .remove();
        this.cell.clear_input();
        return;
      }

      create_panel_cell(text, this.cell.metadata.kernel).execute();
      scrollPanel();
      this.cell.clear_input();
      this.history_index = 0;
    } else if (this.notebook.element[0].contains(document.activeElement)) {
      this.notebook.execute_cell_and_select_below();
    }
  };

  panel.prototype.execute_event = function (evt) {
    // if we execute statements before the kernel is wrapped
    // from other channels (update kernel list etc), wrap it now.
    wrap_execute();

    if (this.cell.element[0].contains(document.activeElement)) {
      let text = this.cell.get_text();
      if (text.trim() === "clear") {
        $("#panel")
          .children()
          .remove();
        this.cell.clear_input();
        return;
      }

      create_panel_cell(text, this.cell.metadata.kernel).execute();
      scrollPanel();
      this.cell.clear_input();
      this.history_index = 0;
    } else if (this.notebook.element[0].contains(document.activeElement)) {
      this.notebook.execute_selected_cells();
    }
  };

  String.prototype.truncate = function () {
    var re = this.match(/^.{0,25}[\S]*/);
    var l = re[0].length;
    var re = re[0].replace(/\s$/, "");
    if (l < this.length) re = re + "...";
    return re;
  };

  var remove_tag = function (cell, tag) {
    // if the toolbar exists, use the button ...
    $(".output_wrapper", cell.element).removeClass(tag);
    if ($(".tags-input", cell.element).length > 0) {
      // find the button and click
      var tag = $(".cell-tag", cell.element).filter(function (idx, y) {
        return y.innerText === tag;
      });
      $(".remove-tag-btn", tag).click();
    } else {
      // otherwise just remove the metadata
      var idx = cell.metadata.tags.indexOf(tag);
      cell.metadata.tags.splice(idx, 1);
    }
  };

  var add_tag = function (cell, tag) {
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
  };

  var toggle_display_output = function (evt) {
    var cell = evt.notebook.get_selected_cell();
    if (cell.cell_type === "markdown") {
      // switch between hide_output and ""
      if (
        cell.metadata.tags &&
        cell.metadata.tags.indexOf("hide_output") >= 0
      ) {
        // if report_output on, remove it
        remove_tag(cell, "hide_output");
      } else {
        add_tag(cell, "hide_output");
      }
    } else if (cell.cell_type === "code") {
      // switch between report_output and ""
      if (
        cell.metadata.tags &&
        cell.metadata.tags.indexOf("report_output") >= 0
      ) {
        // if report_output on, remove it
        remove_tag(cell, "report_output");
      } else {
        add_tag(cell, "report_output");
      }
    }
    // evt.notebook.select_next(true);
    evt.notebook.focus_cell();
  };

  var toggle_cell_kernel = function (evt) {

    var cell = evt.notebook.get_selected_cell();
    if (cell.cell_type !== "code") {
      return;
    }
    // switch to the next used kernel
    let kernels = nb.metadata["sos"]["kernels"];
    // current kernel
    let kernel = cell.metadata["kernel"];
    if (kernels.length <= 1) {
      return;
    }
    // index of kernel
    for (let i = 0; i < kernels.length; ++i) {
      if (kernels[i][0] === kernel) {
        let next = (i + 1) % kernels.length;
        cell.metadata['kernel'] = kernels[next][0];
        changeStyleOnKernel(cell);
        break;
      }
    }
  };

  var paste_table_as_markdown = function (evt) {
    var cell = evt.notebook.get_selected_cell();
    if (cell.cell_type === "markdown") {
      send_kernel_msg({
        "paste-table": []
      });
    }
    // evt.notebook.select_next(true);
    evt.notebook.focus_cell();
  };

  var toggle_markdown_cell = function (evt) {
    var idx = evt.notebook.get_selected_index();
    if (evt.notebook.get_cell(idx).cell_type === "markdown") {
      evt.notebook.to_code(idx);
    } else {
      evt.notebook.to_markdown(idx);
    }
    evt.notebook.focus_cell();
  };

  panel.prototype.move_cursor_up = function (evt) {
    //var cell = nb.get_selected_cell();
    if (this.cell.element[0].contains(document.activeElement)) {
      // in panel
      var cm = this.cell.code_mirror;
      var cur = cm.getCursor();
      let cells = $("#panel").children();
      // 0 ok
      // history_index = 1, length = 1, no
      if (
        this.cell.at_top() &&
        cells.length > 0 &&
        this.history_index < cells.length &&
        cur.ch === 0
      ) {
        if (this.history_index === 0) {
          // save the current cell as index 0 so that we can get back
          this.cell_input = this.cell.get_text();
        }
        this.history_index += 1;
        // if index = 1, we are getting the last cell.
        // if index = cells.length, we are getting the first cell
        let text = cells[
          cells.length - this.history_index
        ].getElementsByClassName("input_area")[0].getElementsByClassName('CodeMirror-sizer')[0].innerText;
        // set text
        this.cell.set_text(text.replace(/\u200B$/g, ""));
      }
      return false;
    } else if (this.notebook.element[0].contains(document.activeElement)) {
      evt.notebook.keyboard_manager.actions.call(
        "jupyter-notebook:move-cursor-up"
      );
      return false;
    }
  };

  panel.prototype.move_cursor_down = function (evt) {
    //var cell = nb.get_selected_cell();
    if (this.cell.element[0].contains(document.activeElement)) {
      if (this.cell.at_bottom() && this.history_index > 0) {
        this.history_index -= 1;
        let text = "";
        if (this.history_index === 0) {
          text = this.cell_input;
        } else {
          // move down from history list
          let cells = $("#panel").children();
          text = cells[
            cells.length - this.history_index
          ].getElementsByClassName("input_area")[0].innerText;
        }
        // set text
        this.cell.set_text(text.replace(/\u200B$/g, ""));
      }
      return false;
    } else if (this.notebook.element[0].contains(document.activeElement)) {
      evt.notebook.keyboard_manager.actions.call(
        "jupyter-notebook:move-cursor-down"
      );
      return false;
    }
  };

  var run_in_console = async function (evt) {
    //var cell = nb.get_selected_cell();
    var cell = evt.notebook.get_selected_cell();
    // if the current cell does not has focus, ignore this shortcut
    if (!nb.get_selected_cell().element[0].contains(document.activeElement))
      return false;

    var text = cell.code_mirror.getSelection();
    let cell_kernel = cell.metadata.kernel;

    if (text === "") {
      // get current line and move the cursor to the next line
      var cm = cell.code_mirror;
      var line_ch = cm.getCursor();
      var cur_line = line_ch["line"];

      let indentation_aware = cell_kernel === 'SoS' || (KernelOptions[cell_kernel] &&
        KernelOptions[cell_kernel]["indentation_aware"])

      text = cm.getLine(cur_line);
      // no selection, find the complete statement around the current line
      let srcLines = cell.get_text().split("\n");
      // indentation levels, -1 for empty lines
      let srcIndents = srcLines.map(x => x.search(/\S/));
      let curLine = line_ch["line"];
      while (curLine < cm.lineCount() && srcIndents[curLine] === -1) {
        curLine += 1;
      }
      // if curLine > 0, we first do a search from beginning
      let fromFirst = curLine > 0;
      let firstLine = 0;
      let lastLine = firstLine + 1;
      while (true) {
        // move to first non-empty line
        while (firstLine < cm.lineCount() && srcIndents[firstLine] === -1) {
          firstLine += 1;
        }
        // if firstLine moves away from an empty line, move lastLine as well
        if (lastLine <= firstLine) {
          lastLine = firstLine + 1;
        }
        // search for lastLine whose indent is equal to or smaller than the first
        if (indentation_aware) {
          while (
            lastLine < cm.lineCount() &&
            (srcIndents[lastLine] === -1 ||
              srcIndents[lastLine] > srcIndents[firstLine])
          ) {
            lastLine += 1;
          }
        }
        text = srcLines.slice(firstLine, lastLine).join("\n");
        let check_completed = new Promise((resolve, reject) => {
          cell.kernel.send_shell_message(
            "is_complete_request",
            {
              code: text + "\n\n"
            },
            {
              shell: {
                reply: reply => {
                  resolve(reply.content.status);
                }
              }
            }
          );
        });

        let completed = await check_completed;
        if (completed === "complete") {
          if (curLine < lastLine) {
            // we find a block of complete statement containing the current line, great!
            while (
              lastLine < cm.lineCount() &&
              srcIndents[lastLine] === -1
            ) {
              lastLine += 1;
            }
            cell.code_mirror.setCursor(lastLine, line_ch["ch"]);
            break;
          } else {
            // discard the complete statement before the current line and continue
            firstLine = lastLine;
            lastLine = firstLine + 1;
          }
        } else if (lastLine < cm.lineCount()) {
          // if incomplete and there are more lines, add the line and check again
          lastLine += 1;
        } else if (fromFirst) {
          // we search from the first line and failed, we search again from current line
          firstLine = curLine;
          lastLine = curLine + 1;
          fromFirst = false;
        } else {
          // if we have searched both from first line and from current line and we
          // cannot find anything, we submit the current line.
          text = srcLines[curLine];
          while (
            curLine + 1 < cm.lineCount() &&
            srcIndents[curLine + 1] === -1
          ) {
            curLine += 1;
          }
          cell.code_mirror.setCursor(curLine + 1, line_ch["ch"]);
          break;
        }
      }
    }
    if (!nb.metadata["sos"]["panel"].displayed) toggle_panel("false");
    //
    window.my_panel.cell.metadata.kernel = cell_kernel;

    if (
      KernelOptions[cell_kernel] &&
      KernelOptions[cell_kernel]["variable_pattern"] &&
      text.match(KernelOptions[cell_kernel]["variable_pattern"])
    ) {
      text = "%preview " + text;
    } else if (
      KernelOptions[cell_kernel] &&
      KernelOptions[cell_kernel]["assignment_pattern"]
    ) {
      var matched = text.match(
        KernelOptions[cell_kernel]["assignment_pattern"]
      );
      if (matched) {
        // keep output in the panel cell...
        text = "%preview -o " + matched[1] + "\n" + text;
      }
    }
    create_panel_cell(text, cell_kernel).execute();
    scrollPanel();
    return false;
  };


  function setup_panel() {
    // lazy, hook it up to Jupyter.notebook as the handle on all the singletons
    console.log("Setting up panel");
    window.my_panel = new panel(Jupyter.notebook);
    Jupyter.notebook.config.loaded.then(
      function () {
        if (Jupyter.notebook.config.data &&
          Jupyter.notebook.config.data.sos &&
          Jupyter.notebook.config.data.sos.notebook_console_panel &&
          Jupyter.notebook.config.data.sos.notebook_console_panel != "auto") {
          //  true or false
          toggle_panel(Jupyter.notebook.config.data.sos.notebook_console_panel);
        } else if (!nb.metadata["sos"]["panel"].displayed) {
          // auto or yes,
          toggle_panel("false");
        } else {
          toggle_panel("true");
        }
      }
    )

  }

  function toggle_panel(force = "auto") {
    let is_open = !$("#notebook-container").hasClass("without_console_panel");

    if ((force == "true" && is_open) || (force == "false" && !is_open)) {
      nb.metadata["sos"]["panel"].displayed = is_open;
      return;
    }
    // toggle draw (first because of first-click behavior)
    //$("#panel-wrapper").toggle({"complete":function(){
    if (is_open) {
      $("#notebook-container").addClass("without_console_panel");
      $("#panel-wrapper").removeClass("active");

      $("#notebook-container").css(
        "margin-left", "auto"
      );
      $("#notebook-container").css(
        "margin-right", "auto"
      );

      nb.metadata["sos"]["panel"].displayed = false;
      console.log("panel closed");

    } else {
      $("#notebook-container").removeClass("without_console_panel");
      $("#panel-wrapper").addClass("active");

      $("#notebook-container").css(
        "margin-left",
        $("#panel-wrapper").width() + 25
      );
      $("#notebook-container").css(
        "width",
        $("#notebook").width() - $("#panel-wrapper").width() - 40
      );

      $("#panel-wrapper").css("height", $("#site").height());
      $("#panel-wrapper").css("top", $("#header").height());

      nb.metadata["sos"]["panel"].displayed = true;
      window.my_panel.cell.focus_editor();

      console.log("panel open");
    }
  }

  function load_panel() {
    load_css(`

#notebook-container.without_console_panel {
  margin-left: auto;
  margin-right: auto;
}

#panel-wrapper.active {
  position: fixed;
  display: flex;
  left: 0px;
}

#panel-wrapper {
  z-index: 10;
  display: none;
}

.panel {
padding: 0px;
overflow-y: auto;
font-weight: normal;
color: #333333;
/* white-space: nowrap; */
overflow-x: auto;
flex: 1 1 auto;
margin-bottom: 10px;
}

.sidebar-wrapper {
  height: 100%;
  left: 5px;
  margin: 5px;
  /* padding-top: 10px; */
  position: fixed !important;
  width: 25%;
  max-width: 50%;
  /* background-color: #F8F5E1; */
  border-style: solid;
  border-color: rgb(171, 171, 171);
  opacity: .99;
  overflow: hidden;
  display: flex;
  flex-direction: column;
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

.ui-icon { display: none !important; }

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

#panel-wrapper .run_this_cell {
  visibility: hidden;
}

.output_area .run_this_cell {
  padding-bottom: 0px;
  padding-top: 0px;
}

div.output_subarea:empty {
  padding: 0px;
}

#panel-wrapper .anchor-cell {
  padding-right: 5pt;
}

#panel-wrapper .console-cell .input_area {
border: none;
/* background: none */;
}

#panel-wrapper .console-output-cell .input {
display: none;
}

#panel-wrapper .console-output-cell .out_prompt_overlay.prompt {
  min-width: 2ex;
}

#panel-wrapper .console-output-cell .prompt {
  display: none;
}

#panel-wrapper .panel-item-num {
font-style: normal;
font-family: Georgia, Times New Roman, Times, serif;
color: black;
}

ul.panel-icons {
list-style: none;
display: flex;
margin-top: -22px;
position: absolute;
left: 25px;
}

.panel-icons li {
padding-right: 1em;
}

pre.section-header.CodeMirror-line {
border-top: 1px dotted #cfcfcf
}

.panel_input_prompt {
/*  position: absolute;
  min-width: 0pt; */
}

.input_dropdown {
float: right;
margin-right: 2pt;
margin-top: 5pt;
z-index: 1000;
}

#panel-wrapper .console-cell .cell_kernel_selector {
display: none;
}

#panel-wrapper .anchor-cell .cell_kernel_selector {
margin-top: -17pt;
margin-right: 0pt;
}


.code_cell .cell_kernel_selector {
  /* width:70pt; */
  background: none;
  z-index: 1000;
  position: absolute;
  height: 1.7em;
  margin-top: 3pt;
  right: 8pt;
  font-size: 80%;
}

.sos_logging {
font-family: monospace;
margin: -0.4em;
padding-left: 0.4em;
}
.sos_hint {
color: gray;
font-family: monospace;
}

.sos_debug {
color: blue;
}

.sos_trace {
color: darkcyan;
}

.sos_hilight {
color: green;
}

.sos_info {
  color: black;
}

.sos_warning {
color: black;
background: #fdd
}

.sos_error {
color: black;
background: #fdd
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

time.pending, time.submitted, time.running,


table.workflow_table,
table.task_table {
border: 0px;
}


table.workflow_table i,
table.task_table i  {
margin-right: 5px;
}

td.workflow_name
{
width: 10em;
text-align: left;
}

td.workflow_name pre,
td.task_name pre {
font-size: 1.2em;
}

td.workflow_id,
td.task_id
{
width: 15em;
text-align: left;
}

td.task_tags
{
text-align: left;
max-width: 33em;
}

td.task_id
{
text-align: left;
}

td.task_id span,
td.task_tags span {
display: inline-flex;
}

td.task_tags span pre {
padding-right: 0.5em;
}

td.task_tags i  {
margin-right: 0px;
}

.task_id_actions,
.task_tag_actions {
display: none;
}

.task_id_actions .fa:hover,
.task_tag_actions .fa:hover {
color: blue;
}

.task_id:hover .task_id_actions,
.task_tags:hover .task_tag_actions {
display: flex;
flex-direction: row;
}

td.workflow_index
{
width: 5em;
text-align: left;
}

td.workflow_status
{
width: 20em;
text-align: left;
}

td.task_timer
{
width: 15em;
text-align: left;
}

td.task_timer pre
{
text-overflow: ellipsis;
overflow: hidden;
white-space: nowrap;
}


td.task_icon {
  font-size: 0.75em;
}

td.task_status,
{
width: 15em;
text-align: left;
}

table.workflow_table span {
/* text-transform: uppercase; */
font-family: monospace;
}

table.task_table span {
/* text-transform: uppercase; */
font-family: monospace;
}

table.workflow_table.pending pre,
table.task_table.pending pre,
table.task_table.submitted pre,
table.task_table.missing pre {
color: #9d9d9d; /* gray */
}

table.workflow_table.running pre,
table.task_table.running pre {
color: #cdb62c; /* yellow */
}

table.workflow_table.completed pre,
table.task_table.completed pre {
color: #39aa56; /* green */
}

table.workflow_table.aborted pre,
table.task_table.aborted pre {
color: #FFA07A; /* salmon */
}

table.workflow_table.failed pre,
table.task_table.failed pre {
color: #db4545; /* red */
}

table.task_table {
border: 0px;
border-style: solid;
}
.code_cell .cm-header-1,
.code_cell .cm-header-2,
.code_cell .cm-header-3,
.code_cell .cm-header-4,
.code_cell .cm-header-5,
.code_cell .cm-header-6
{
  font-size: 100%;
  font-style: normal;
  font-weight: normal;
  font-family: monospace;
}

.task_hover {
color: black !important;
}

/* side panel */
#panel-wrapper #panel div.output_area {
display: -webkit-box;
}

#panel-wrapper #panel div.output_subarea {
max_width: 100%;
}

#panel-wrapper #panel .output_scroll {
height: auto;
}

.anchor-cell {
bottom: 5px;
margin-right: 5px;
flex: 0 0 auto;
margin-top: 2em !important;
}

.cm-sos-interpolated {
background-color: rgb(223, 144, 207, 0.4);
}
.cm-sos-sigil {
background-color: rgb(223, 144, 207, 0.4);
}
/*
.cm-sos-script {
font-style: normal;
}

.cm-sos-option {
font-style: italic;
} */


.panel-icons li:hover {
color: green;
}


.bs-callout {
    padding: 20px;
    margin: 20px 0;
    border: 1px solid #eee;
    border-left-width: 5px;
    border-radius: 3px;
}
.bs-callout h4 {
    margin-top: 0 !important;
    margin-bottom: 5px;
    font-weight: 500;
    line-height: 1.1;
    display: block;
    margin-block-start: 1.33em;
    margin-block-end: 1.33em;
    margin-inline-start: 0px;
    margin-inline-end: 0px;
}
.bs-callout p:last-child {
    margin-bottom: 0;
}
.bs-callout code {
    border-radius: 3px;
}
.bs-callout+.bs-callout {
    margin-top: -5px;
}
.bs-callout-default {
    border-left-color: #777;
}
.bs-callout-default h4 {
    color: #777;
}
.bs-callout-primary {
    border-left-color: #428bca;
}
.bs-callout-primary h4 {
    color: #428bca;
}
.bs-callout-success {
    border-left-color: #5cb85c;
}
.bs-callout-success h4 {
    color: #5cb85c;
}
.bs-callout-danger {
    border-left-color: #d9534f;
}
.bs-callout-danger h4 {
    color: #d9534f;
}
.bs-callout-warning {
    border-left-color: #f0ad4e;
}
.bs-callout-warning h4 {
    color: #f0ad4e;
}
.bs-callout-info {
    border-left-color: #5bc0de;
}
.bs-callout-info h4 {
    color: #5bc0de;
}
`);

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
      IPython.toolbar.add_buttons_group([
        {
          label: "Console",
          icon: "fa-cube",
          callback: toggle_panel,
          id: "panel_button"
        }
      ]);
    }
  }

  function safe_css_name(name) {
    return name.replace(/[^a-z0-9_]/g, function (s) {
      var c = s.charCodeAt(0);
      if (c == 32) return "-";
      if (c >= 65 && c <= 90) return "_" + s.toLowerCase();
      return "__" + ("000" + c.toString(16)).slice(-4);
    });
  }

  function patch_CodeCell_get_callbacks() {
    var previous_get_callbacks = CodeCell.prototype.get_callbacks;
    CodeCell.prototype.get_callbacks = function () {
      var that = this;
      var callbacks = previous_get_callbacks.apply(this, arguments);
      var prev_reply_callback = callbacks.shell.reply;
      callbacks.shell.reply = function (msg) {
        return prev_reply_callback(msg);
      };
      return callbacks;
    };
  }

  function add_lan_selector(cell) {
    // for a new cell? NOTE that the cell could be a markdown cell.
    // A selector would be added although not displayed.
    if (!cell.metadata.kernel) {
      var idx = nb.find_cell_index(cell);
      var kernel = "SoS";
      if (idx > 0) {
        for (idx = idx - 1; idx >= 0; --idx) {
          if (nb.get_cell(idx).cell_type === "code") {
            kernel = nb.get_cell(idx).metadata["kernel"];
            break;
          }
        }
      }
      cell.metadata.kernel = kernel;
    }
    var kernel = cell.metadata.kernel;
    if (
      cell.element[0].getElementsByClassName("cell_kernel_selector").length > 0
    ) {
      // update existing list
      var select = $(".cell_kernel_selector", cell.element).empty();
      for (var i = 0; i < window.KernelList.length; i++) {
        select.append(
          $("<option/>")
            .attr("value", window.DisplayName[window.KernelList[i]])
            .text(window.DisplayName[window.KernelList[i]])
        );
      }
      select.val(kernel);
      return;
    }
    // add a new one
    var select = $("<select/>")
      .attr("id", "cell_kernel_selector")
      .css("margin-left", "0.75em")
      .attr("class", "select-xs cell_kernel_selector");
    for (var i = 0; i < window.KernelList.length; i++) {
      select.append(
        $("<option/>")
          .attr("value", window.DisplayName[window.KernelList[i]])
          .text(window.DisplayName[window.KernelList[i]])
      );
    }
    select.val(kernel);

    select.change(function () {
      cell.metadata.kernel = window.DisplayName[this.value];
      send_kernel_msg({
        "set-editor-kernel": cell.metadata.kernel
      });

      let kernel_name = window.KernelName[this.value];
      if (kernel_name !== "sos" && !window.JsLoaded[kernel_name]) {
        load_kernel_js(kernel_name);
      }
      $(cell.element)
        .removeClass((index, className) => {
          return (className.match(/(^|\s)sos_lan_\S+/g) || []).join(" ");
        })
        .addClass(safe_css_name(`sos_lan_${this.value}`));
      // https://github.com/vatlab/sos-notebook/issues/55

      cell.user_highlight = {
        name: "sos",
        base_mode: window.CodeMirrorMode[this.value] ||
          window.LanguageName[this.value] ||
          kernel_name ||
          this.value
      };
      //console.log(`Set cell code mirror mode to ${cell.user_highlight.base_mode}`)
      cell.code_mirror.setOption("mode", cell.user_highlight);
      save_kernel_info();
    });

    cell.element.find("div.input_area").prepend(select);
    return select;
  }

  function add_panel_icons(cell) {
    let ul = $("<ul/>")
      .addClass("panel-icons")
      .append('<li class="icon_save"><i class="fa fa-file-text-o"></i></li>')
      .append('<li class="icon_workflow"><i class="fa fa-code"></i></li>');
    cell.element.find("div.input_area").prepend(ul);
  }

  function highlight_cells(cells, i, interval) {
    setTimeout(function () {
      if (cells[i].cell_type === "code" && cells[i].user_highlight) {
        // console.log(`set ${cells[i].user_highlight} for cell ${i}`);
        cells[i].code_mirror.setOption(
          "mode",
          cells[i].user_highlight === "auto" ? "sos" : cells[i].user_highlight
        );
      }
      if (i < cells.length - 1) highlight_cells(cells, i + 1, interval);
    }, interval);
  }

  var onload = function () {
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
      events.on("kernel_connected.Kernel", function () {
        register_sos_comm();
        wrap_execute();
      });
    }
    events.on("create.Cell", function (evt, param) {
      add_lan_selector(param.cell);
      changeStyleOnKernel(param.cell);
    });
    //
    // restart kernel does not clear existing side panel.
    events.on("kernel_connected.Kernel", function () {
      // Issue #1: need to re-register sos_comm after kernel is restarted.
      register_sos_comm();
    });
    // #550
    events.on("select.Cell", notify_cell_kernel);

    load_panel();
    add_panel_button();

    // add_download_menu();
    patch_CodeCell_get_callbacks();

    $("li.icon_save").on("click", function () {
      // we are letting the li bind to the event
      create_panel_cell("%sossave --to html --force").execute();
      scrollPanel();
    });
    $("li.icon_workflow").on("click", function () {
      // we are letting the li bind to the event
      create_panel_cell("%preview --workflow").execute();
      scrollPanel();
    });

    events.on("kernel_ready.Kernel", function () {
      /* #524. After kernel ready, jupyter would broad cast
       * codemirror mode to all cells, which will overwrite the
       * user mode we have just set. We have no choice but to
       * set codemirror mode again.
       * */
      //nb.set_codemirror_mode("sos");
      highlight_cells(nb.get_cells(), 0, 100);
    });

    // define SOS CodeMirror syntax highlighter
    (function (mod) {
      //if (typeof exports === "object" && typeof module === "object") // CommonJS
      // mod(require("../../lib/codemirror"));
      //else if (typeof define === "function" && define.amd) // AMD
      //  define(["../../lib/codemirror"], mod);
      //else // Plain browser env
      mod(CodeMirror);
    })(function (CodeMirror) {
      "use strict";

      var sosKeywords = ["input", "output", "depends", "parameter"];
      var sosActionWords = [
        "script",
        "download",
        "run",
        "bash",
        "sh",
        "csh",
        "tcsh",
        "zsh",
        "python",
        "python2",
        "python3",
        "R",
        "node",
        "julia",
        "matlab",
        "octave",
        "ruby",
        "perl",
        "report",
        "pandoc",
        "docker_build",
        "Rmarkdown"
      ];
      var sosMagicWords = [
        "cd",
        "capture",
        "clear",
        "debug",
        "dict",
        "expand",
        "get",
        "matplotlib",
        "paste",
        "preview",
        "pull",
        "push",
        "put",
        "render",
        "rerun",
        "run",
        "save",
        "sandbox",
        "set",
        "sessioninfo",
        "sosrun",
        "sossave",
        "shutdown",
        "taskinfo",
        "tasks",
        "use",
        "with"
      ];
      var sosFunctionWords = ["sos_run", "logger", "get_output"];

      var hintWords = sosKeywords
        .concat(sosActionWords)
        .concat(sosFunctionWords)
        .concat(sosMagicWords);

      var sosDirectives = sosKeywords.map(x => x + ":");
      var sosActions = sosActionWords.map(x => new RegExp("^\\s*" + x + ":"));
      var sosMagics = sosMagicWords.map(x => "%" + x);

      // hint word for SoS mode
      CodeMirror.registerHelper("hintWords", "sos", hintWords);

      function findMode(mode) {
        if (Jupyter.notebook.config.data && Jupyter.notebook.config.data.sos &&
          Jupyter.notebook.config.data.sos.kernel_codemirror_mode) {
          let modeMap = Jupyter.notebook.config.data.sos.kernel_codemirror_mode;
          if (mode in modeMap) {
            return modeMap[mode];
          } else if (typeof mode === 'string' && mode.toLowerCase() in modeMap) {
            return modeMap[mode.toLowerCase()]
          }
        }
        return null;
      }

      function findModeFromFilename(filename) {
        var val = filename, m, mode, spec;
        if (m = /.+\.([^.]+)$/.exec(val)) {
          var info = CodeMirror.findModeByExtension(m[1]);
          if (info) {
            mode = info.mode;
            spec = info.mime;
          }
        } else if (/\//.test(val)) {
          var info = CodeMirror.findModeByMIME(val);
          if (info) {
            mode = info.mode;
            spec = val;
          }
        } else {
          mode = spec = val;
        }
        return 'mode';
      }

      function markExpr(python_mode) {
        return {
          startState: function () {
            return {
              in_python: false,
              sigil: null,
              matched: true,
              python_state: CodeMirror.startState(python_mode)
            };
          },

          copyState: function (state) {
            return {
              in_python: state.in_python,
              sigil: state.sigil,
              matched: state.matched,
              python_state: CodeMirror.copyState(
                python_mode,
                state.python_state
              )
            };
          },

          token: function (stream, state) {
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
                return (
                  "sos-interpolated error" +
                  (state.matched ? "" : " sos-unmatched")
                );
              }
              if (it == "variable" || it == "builtin") {
                let ct = stream.current();
                // warn users in the use of input and output in {}
                if (ct === "input" || ct === "output") it += " error";
              }
              return (
                (it ? "sos-interpolated " + it : "sos-interpolated") +
                (state.matched ? "" : " sos-unmatched")
              );
            } else {
              // remove the double brace case, the syntax highlighter
              // does not have to worry (highlight) }}, although it would
              // probably mark an error for single }
              if (state.sigil.left === "{" && stream.match(/\{\{/)) return null;
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
              while (stream.next() && !stream.match(state.sigil.left, false)) { }
              return null;
            }
          }
        };
      }

      CodeMirror.defineMode(
        "sos",
        function (conf, parserConf) {
          // conf appears to be used only for nested mode
          // parserConf is an object similar to the mode option.
          let sosPythonConf = {};
          for (let prop in parserConf) {
            if (parserConf.hasOwnProperty(prop)) {
              sosPythonConf[prop] = parserConf[prop];
            }
          }
          sosPythonConf.name = "python";
          sosPythonConf.version = 3;
          sosPythonConf.extra_keywords = sosActionWords.concat(
            sosFunctionWords
          );

          // this is the SoS flavored python mode with more identifiers
          var base_mode = null;
          if ("base_mode" in parserConf && parserConf.base_mode) {
            let spec = findMode(parserConf.base_mode);
            if (spec) {
              let modename = spec
              if (typeof spec != "string") {
                modename = spec.name
              }
              if (!CodeMirror.modes.hasOwnProperty(modename)) {
                console.log(`Load codemirror mode ${modename}`);
                CodeMirror.requireMode(modename, function () { }, {});
              }
              base_mode = CodeMirror.getMode(conf, spec);
              // base_mode = CodeMirror.getMode(conf, mode);
            } else {
              base_mode = CodeMirror.getMode(conf, parserConf.base_mode);
            }
            // } else {
            //   console.log(`No base mode is found for ${parserConf.base_mode}. Python mode used.`);
            // }
          }
          // if there is a user specified base mode, this is the single cell mode
          if (base_mode) {
            var python_mode = CodeMirror.getMode(
              {},
              {
                name: "python",
                version: 3
              }
            );

            var overlay_mode = markExpr(python_mode);
            return {
              startState: function () {
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

              copyState: function (state) {
                return {
                  sos_mode: state.sos_mode,
                  base_state: CodeMirror.copyState(base_mode, state.base_state),
                  overlay_state: CodeMirror.copyState(
                    overlay_mode,
                    state.overlay_state
                  ),
                  // for overlay
                  basePos: state.basePos,
                  baseCur: null,
                  overlayPos: state.overlayPos,
                  overlayCur: null
                };
              },

              token: function (stream, state) {
                if (state.sos_mode) {
                  if (stream.sol()) {
                    let sl = stream.peek();
                    if (sl == "!") {
                      stream.skipToEnd();
                      return "meta";
                    } else if (sl == "#") {
                      stream.skipToEnd();
                      return "comment";
                    }
                    for (var i = 0; i < sosMagics.length; i++) {
                      if (stream.match(sosMagics[i])) {
                        if (sosMagics[i] === "%expand") {
                          // if there is no :, the easy case
                          if (stream.eol() || stream.match(/\s*(-i\s*\S+|--in\s*\S+)?$/, false)) {
                            state.overlay_state.sigil = {
                              left: "{",
                              right: "}"
                            };
                          } else {
                            let found = stream.match(/\s+(\S+)\s+(\S+)\s*(-i\s*\S+|--in\s*\S+)?$/, false);
                            if (found) {
                              state.overlay_state.sigil = {
                                left: found[1].match(/^.*[A-Za-z]$/) ? found[1] + ' ' : found[1],
                                right: found[2].match(/^[A-Za-z].*$/) ? ' ' + found[2] : found[2]
                              };
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
                  if (
                    stream != state.streamSeen ||
                    Math.min(state.basePos, state.overlayPos) < stream.start
                  ) {
                    state.streamSeen = stream;
                    state.basePos = state.overlayPos = stream.start;
                  }

                  if (stream.start == state.basePos) {
                    state.baseCur = base_mode.token(stream, state.base_state);
                    state.basePos = stream.pos;
                  }
                  if (stream.start == state.overlayPos) {
                    stream.pos = stream.start;
                    state.overlayCur = overlay_mode.token(
                      stream,
                      state.overlay_state
                    );
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

              indent: function (state, textAfter) {
                // inner indent
                if (!state.sos_mode) {
                  if (!base_mode.indent) return CodeMirror.Pass;
                  return base_mode.indent(state.base_state, textAfter);
                } else {
                  // sos mode has no indent
                  return 0;
                }
              },

              innerMode: function (state) {
                return state.sos_mode
                  ? {
                    state: state.base_state,
                    mode: base_mode
                  }
                  : null;
              },

              lineComment: "#",
              fold: "indent"
            };
          } else {
            // this is SoS mode
            base_mode = CodeMirror.getMode(conf, sosPythonConf);
            overlay_mode = markExpr(base_mode);
            return {
              startState: function () {
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

              copyState: function (state) {
                return {
                  sos_state: state.sos_state,
                  base_state: CodeMirror.copyState(base_mode, state.base_state),
                  overlay_state: CodeMirror.copyState(
                    overlay_mode,
                    state.overlay_state
                  ),
                  inner_mode: state.inner_mode,
                  inner_state:
                    state.inner_mode &&
                    CodeMirror.copyState(state.inner_mode, state.inner_state),
                  // for overlay
                  basePos: state.basePos,
                  baseCur: null,
                  overlayPos: state.overlayPos,
                  overlayCur: null
                };
              },

              token: function (stream, state) {
                if (stream.sol()) {
                  let sl = stream.peek();
                  if (sl == "[") {
                    // header, move to the end
                    if (stream.match(/^\[.*\]$/, false)) {
                      // if there is :
                      if (stream.match(/^\[[\s\w_,-]+:/)) {
                        state.sos_state = "header_option";
                        return "header line-section-header";
                      } else if (stream.match(/^\[[\s\w,-]+\]$/)) {
                        // reset state
                        state.sos_state = null;
                        state.inner_mode = null;
                        return "header line-section-header";
                      }
                    }
                  } else if (sl == "!") {
                    stream.eatWhile(/\S/);
                    return "meta";
                  } else if (sl == "#") {
                    stream.skipToEnd();
                    return "comment";
                  } else if (sl == "%") {
                    stream.eatWhile(/\S/);
                    return "meta";
                  } else if (
                    state.sos_state &&
                    state.sos_state.startsWith("entering ")
                  ) {
                    // the second parameter is starting column
                    let mode = findMode(state.sos_state.slice(9).toLowerCase());
                    if (mode) {
                      state.inner_mode = CodeMirror.getMode(conf, mode);
                      state.inner_state = CodeMirror.startState(
                        state.inner_mode,
                        stream.indentation()
                      );
                      state.sos_state = null;
                    } else {
                      state.sos_state = 'unknown_language';
                    }
                    state.sos_indent = stream.indentation();
                  }
                  if (stream.indentation() === 0 &&
                    ((state.inner_mode &&
                      stream.indentation() < state.sos_indent
                    ) || state.sos_state == 'unknown_language')) {
                    state.inner_mode = null;
                    state.sos_state = null;
                  }
                  for (var i = 0; i < sosDirectives.length; i++) {
                    if (stream.match(sosDirectives[i])) {
                      // the rest of the lines will be processed as Python code
                      state.sos_state = "directive_option";
                      return "keyword strong";
                    }
                  }
                  for (var i = 0; i < sosActions.length; i++) {
                    if (stream.match(sosActions[i])) {
                      // switch to submode?
                      if (stream.eol()) {
                        // really
                        let mode = findMode(
                          stream
                            .current()
                            .slice(0, -1)
                            .toLowerCase()
                        );
                        if (mode) {
                          state.sos_state =
                            "entering " + stream.current().slice(0, -1);
                        } else {
                          state.sos_state = "entering unknown_language";
                        }
                      } else {
                        state.sos_state =
                          "start " + stream.current().slice(0, -1);
                      }
                      state.overlay_state.sigil = null;
                      return "builtin strong";
                    }
                  }
                  // if unknown action
                  if (stream.match(/\w+:/)) {
                    state.overlay_state.sigil = null;
                    state.sos_state = "start " + stream.current().slice(0, -1);
                    return "builtin strong";
                  }
                } else if (state.sos_state == "header_option") {
                  // stuff after :
                  if (stream.peek() == "]") {
                    // move next
                    stream.next();
                    // ] is the last char
                    if (stream.eol()) {
                      state.sos_state = null;
                      state.inner_mode = null;
                      return "header line-section-header";
                    } else {
                      stream.backUp(1);
                      let it = base_mode.token(stream, state.base_state);
                      return it ? it + " sos-option" : null;
                    }
                  } else {
                    let it = base_mode.token(stream, state.base_state);
                    return it ? it + " sos-option" : null;
                  }
                } else if (state.sos_state == "directive_option") {
                  // stuff after input:, R: etc
                  if (stream.peek() == ",") {
                    // move next
                    stream.next();
                    // , is the last char, continue option line
                    if (stream.eol()) {
                      stream.backUp(1);
                      let it = base_mode.token(stream, state.base_state);
                      return it ? it + " sos-option" : null;
                    }
                    stream.backUp(1);
                  } else if (stream.eol()) {
                    // end of line stops option mode
                    state.sos_state = null;
                    state.inner_mode = null;
                  }
                  let it = base_mode.token(stream, state.base_state);
                  return it ? it + " sos-option" : null;
                } else if (
                  state.sos_state &&
                  state.sos_state.startsWith("start ")
                ) {
                  // try to understand option expand=
                  if (stream.match(/^.*expand\s*=\s*True/, false)) {
                    // highlight {}
                    state.overlay_state.sigil = {
                      left: "{",
                      right: "}"
                    };
                  } else {
                    let found = stream.match(
                      /^.*expand\s*=\s*"(\S+) (\S+)"/,
                      false
                    );
                    if (!found)
                      found = stream.match(/^.*expand\s*=\s*'(\S+) (\S+)'/, false);
                    if (found) {
                      state.overlay_state.sigil = {
                        left: found[1].match(/^.*[A-Za-z]$/) ? found[1] + ' ' : found[1],
                        right: found[2].match(/^[A-Za-z].*$/) ? ' ' + found[2] : found[2]
                      };
                    }
                  }
                  let mode_string = state.sos_state.slice(6).toLowerCase();
                  // for report, we need to find "output" option
                  if (mode_string === "report" &&
                    stream.match(/^.*output\s*=\s*/, false)) {
                    let found = stream.match(/^.*output\s*=\s*[rRbufF]*"""([^"]+)"""/, false);
                    if (!found)
                      found = stream.match(/^.*output\s*=\s*[rRbufF]*'''([^.]+)'''/, false);
                    if (!found)
                      found = stream.match(/^.*output\s*=\s*[rRbufF]*"([^"]+)"/, false);
                    if (!found)
                      found = stream.match(/^.*output\s*=\s*[rRbufF]*'([^']+)'/, false);

                    // found[1] is the filename
                    state.sos_state = 'start ' + findModeFromFilename(found ? found[1] : found);
                  }
                  let token = base_mode.token(stream, state.base_state);
                  // if it is end of line, ending the starting switch mode
                  if (stream.eol() && stream.peek() !== ",") {
                    // really
                    let mode = findMode(state.sos_state.slice(6).toLowerCase());
                    if (mode) {
                      state.sos_state = "entering " + state.sos_state.slice(6);
                    } else {
                      state.sos_state = "entering unknown_language";
                    }
                  }
                  return token + " sos-option";
                }
                // can be start of line but not special
                if (state.sos_state == "unknown_language") {
                  // we still handle {} in no man unknown_language
                  if (state.overlay_state.sigil) {
                    return overlay_mode.token(stream, state.overlay_state);
                  } else {
                    stream.skipToEnd();
                    return null;
                  }
                } else if (state.inner_mode) {
                  let it = "sos_script ";
                  if (!state.overlay_state.sigil) {
                    let st = state.inner_mode.token(stream, state.inner_state);
                    return st ? it + st : null;
                  } else {
                    // overlay mode, more complicated
                    if (
                      stream != state.streamSeen ||
                      Math.min(state.basePos, state.overlayPos) < stream.start
                    ) {
                      state.streamSeen = stream;
                      state.basePos = state.overlayPos = stream.start;
                    }

                    if (stream.start == state.basePos) {
                      state.baseCur = state.inner_mode.token(
                        stream,
                        state.inner_state
                      );
                      state.basePos = stream.pos;
                    }
                    if (stream.start == state.overlayPos) {
                      stream.pos = stream.start;
                      state.overlayCur = overlay_mode.token(
                        stream,
                        state.overlay_state
                      );
                      state.overlayPos = stream.pos;
                    }
                    stream.pos = Math.min(state.basePos, state.overlayPos);
                    // state.overlay.combineTokens always takes precedence over combine,
                    // unless set to null
                    return (
                      (state.overlayCur ? state.overlayCur : state.baseCur) +
                      " sos-script"
                    );
                  }
                } else {
                  return base_mode.token(stream, state.base_state);
                }
              },

              indent: function (state, textAfter) {
                // inner indent
                if (state.inner_mode) {
                  if (!state.inner_mode.indent) return CodeMirror.Pass;
                  return (
                    state.inner_mode.indent(state.inner_mode, textAfter) + 2
                  );
                } else {
                  return base_mode.indent(state.base_state, textAfter);
                }
              },

              innerMode: function (state) {
                return state.inner_mode
                  ? null
                  : {
                    state: state.base_state,
                    mode: base_mode
                  };
              },

              lineComment: "#",
              fold: "indent",
              electricInput: /^\s*[\}\]\)]$/
            };
          }
        },
        "python"
      );

      CodeMirror.defineMIME("text/x-sos", "sos");
      // bug vatlab / sos - notebook #55
      CodeMirror.autoLoadMode = function () { };
    });
  };

  return {
    onload: onload
  };
});
