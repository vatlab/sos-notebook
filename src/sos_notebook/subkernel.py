import fnmatch

from sos.utils import env


class subkernel(object):
    # a class to information on subkernel
    def __init__(self, name=None, kernel=None, language='', color='', options={}, codemirror_mode=''):
        self.name = name
        self.kernel = kernel
        self.language = language
        self.color = color
        self.options = options
        self.codemirror_mode = codemirror_mode

    def __repr__(self):
        return f'subkernel {self.name} with kernel {self.kernel} for language {self.language} with color {self.color}'


class Subkernels(object):
    # a collection of subkernels
    def __init__(self, kernel):
        self.sos_kernel = kernel
        self.language_info = kernel.supported_languages

        from jupyter_client.kernelspec import KernelSpecManager
        km = KernelSpecManager()
        specs = km.find_kernel_specs()
        # get supported languages
        self._kernel_list = []
        lan_map = {}
        for x in self.language_info.keys():
            for lname, knames in kernel.supported_languages[x].supported_kernels.items():
                for kname in knames:
                    if x != kname:
                        lan_map[kname] = (lname, self.get_background_color(self.language_info[x], lname),
                                          getattr(self.language_info[x], 'options', {}), '')
        # kernel_list has the following items
        #
        # 1. displayed name
        # 2. kernel name
        # 3. language name
        # 4. color
        for spec in specs.keys():
            if spec == 'sos':
                # the SoS kernel will be default theme color.
                self._kernel_list.append(
                    subkernel(
                        name='SoS',
                        kernel='sos',
                        options={
                            'variable_pattern': r'^\s*[_A-Za-z][_A-Za-z0-9\.]*\s*$',
                            'assignment_pattern': r'^\s*([_A-Za-z0-9\.]+)\s*=.*$'
                        },
                        codemirror_mode='sos'))
            elif spec in lan_map:
                # e.g. ir ==> R
                self._kernel_list.append(
                    subkernel(
                        name=lan_map[spec][0],
                        kernel=spec,
                        language=lan_map[spec][0],
                        color=lan_map[spec][1],
                        options=lan_map[spec][2]))
            elif any(fnmatch.fnmatch(spec, x) for x in lan_map.keys()):
                matched = [y for x, y in lan_map.items() if fnmatch.fnmatch(spec, x)][0]
                self._kernel_list.append(
                    subkernel(name=matched[0], kernel=spec, language=matched[0], color=matched[1], options=matched[2]))
            else:
                lan_name = km.get_kernel_spec(spec).language
                if lan_name == 'python':
                    lan_name = 'python3'
                avail_names = [x for x in lan_map.keys() if x.lower() == lan_name.lower()]
                if avail_names:
                    self._kernel_list.append(
                        subkernel(
                            name=spec,
                            kernel=spec,
                            language=lan_map[avail_names[0]][0],
                            color=lan_map[avail_names[0]][1],
                            options=lan_map[avail_names[0]][2]))
                else:
                    # undefined language also use default theme color
                    self._kernel_list.append(
                        subkernel(name=km.get_kernel_spec(spec).display_name, kernel=spec, language=lan_name))

    def kernel_list(self):
        return self._kernel_list

    default_cm_mode = {
        'sos': '',
        'python': {
            'name': 'python',
            'version': 3
        },
        'python2': {
            'name': 'python',
            'version': 2
        },
        'python3': {
            'name': 'python',
            'version': 3
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
            'name': "javascript",
            'typescript': True
        },
        'octave': 'octave',
        'matlab': 'octave',
    }

    # now, no kernel is found, name has to be a new name and we need some definition
    # if kernel is defined
    def add_or_replace(self, kdef):
        for idx, x in enumerate(self._kernel_list):
            if x.name == kdef.name:
                self._kernel_list[idx] = kdef
                return self._kernel_list[idx]
            self._kernel_list.append(kdef)
            return self._kernel_list[-1]

    def get_background_color(self, plugin, lan):
        # if a single color is defined, it is used for all supported
        # languages
        if isinstance(plugin.background_color, str):
            # return the same background color for all inquiry
            return plugin.background_color
        # return color for specified, or any color if unknown inquiry is made
        return plugin.background_color.get(lan, next(iter(plugin.background_color.values())))

    def find(self, name, kernel=None, language=None, color=None, codemirror_mode='', notify_frontend=True):
        codemirror_mode = codemirror_mode if codemirror_mode else self.default_cm_mode.get(
            'codemirror_mode', codemirror_mode)

        # find from subkernel name
        def update_existing(idx):
            x = self._kernel_list[idx]

            #  [Bash, some_sh, ....]
            # but the provided kernel does not match...
            if (kernel is not None and kernel != x.kernel):
                #env.logger.warning(
                #    f"Overriding kernel {x.kernel} used by subkernel {x.name} with kernel {kernel}."
                #)
                # self._kernel_list[idx].kernel = kernel
                if notify_frontend:
                    self.notify_frontend()
            #  similarly, identified by kernel but language names are different
            if language not in (None, '', 'None') and language != x.language:
                env.logger.warning(
                    f"Overriding language {x.language} used by subkernel {x.name} with language {language}.")
                self._kernel_list[idx].language = language
                if notify_frontend:
                    self.notify_frontend()
            if codemirror_mode:
                self._kernel_list[idx].codemirror_mode = codemirror_mode
            if color is not None:
                if color == 'default':
                    if self._kernel_list[idx].language:
                        self._kernel_list[idx].color = self.get_background_color(
                            self.language_info[self._kernel_list[idx].language], self._kernel_list[idx].language)
                    else:
                        self._kernel_list[idx].color = ''
                else:
                    self._kernel_list[idx].color = color
                if notify_frontend:
                    self.notify_frontend()

        # if the language module cannot be loaded for some reason
        if name in self.sos_kernel._failed_languages:
            raise self.sos_kernel._failed_languages[name]
        # find from language name (subkernel name, which is usually language name)
        for idx, x in enumerate(self._kernel_list):
            if x.name == name:
                if x.name == 'SoS' or x.language or language is None:
                    update_existing(idx)
                    return x
                if not kernel:
                    kernel = name
                break
        # find from kernel name
        for idx, x in enumerate(self._kernel_list):
            if x.kernel == name:
                # if exist language or no new language defined.
                if x.language or language is None:
                    update_existing(idx)
                    return x
                # otherwise, try to use the new language
                kernel = name
                break

        if kernel is not None:
            # in this case kernel should have been defined in kernel list
            if kernel not in [x.kernel for x in self._kernel_list]:
                raise ValueError(
                    f'Unrecognized Jupyter kernel name {kernel}. Please make sure it is properly installed and appear in the output of command "jupyter kenelspec list"'
                )
            # now this a new instance for an existing kernel
            kdef = [x for x in self._kernel_list if x.kernel == kernel][0]
            if not language:
                if color == 'default':
                    if kdef.language:
                        color = self.get_background_color(self.language_info[kdef.language], kdef.language)
                    else:
                        color = kdef.color
                new_def = self.add_or_replace(
                    subkernel(
                        name,
                        kdef.kernel,
                        kdef.language,
                        kdef.color if color is None else color,
                        getattr(self.language_info[kdef.language], 'options', {}) if kdef.language else {},
                        codemirror_mode=codemirror_mode))
                if notify_frontend:
                    self.notify_frontend()
                return new_def

            # if language is defined,
            if ':' in language:
                # if this is a new module, let us create an entry point and load
                from pkg_resources import EntryPoint
                mn, attr = language.split(':', 1)
                ep = EntryPoint(name=kernel, module_name=mn, attrs=tuple(attr.split('.')))
                try:
                    plugin = ep.resolve()
                    self.language_info[name] = plugin
                    # for convenience, we create two entries for, e.g. R and ir
                    # but only if there is no existing definition
                    for supported_lan, supported_kernels in plugin.supported_kernels.items():
                        for supported_kernel in supported_kernels:
                            if name != supported_kernel and supported_kernel not in self.language_info:
                                self.language_info[supported_kernel] = plugin
                        if supported_lan not in self.language_info:
                            self.language_info[supported_lan] = plugin
                except Exception as e:
                    raise RuntimeError(f'Failed to load language {language}: {e}') from e
                #
                if color == 'default':
                    color = self.get_background_color(plugin, kernel)
                new_def = self.add_or_replace(
                    subkernel(
                        name,
                        kdef.kernel,
                        kernel,
                        kdef.color if color is None else color,
                        getattr(plugin, 'options', {}),
                        codemirror_mode=codemirror_mode))
            else:
                # if should be defined ...
                if language not in self.language_info:
                    raise RuntimeError(
                        f'Unrecognized language definition {language}, which should be a known language name or a class in the format of package.module:class'
                    )
                #
                self.language_info[name] = self.language_info[language]
                if color == 'default':
                    color = self.get_background_color(self.language_info[name], language)
                new_def = self.add_or_replace(
                    subkernel(
                        name,
                        kdef.kernel,
                        language,
                        kdef.color if color is None else color,
                        getattr(self.language_info[name], 'options', {}),
                        codemirror_mode=codemirror_mode))
            if notify_frontend:
                self.notify_frontend()
            return new_def

        if language is not None:
            # kernel is not defined and we only have language
            if ':' in language:
                # if this is a new module, let us create an entry point and load
                from pkg_resources import EntryPoint
                mn, attr = language.split(':', 1)
                ep = EntryPoint(name='__unknown__', module_name=mn, attrs=tuple(attr.split('.')))
                try:
                    plugin = ep.resolve()
                    self.language_info[name] = plugin
                except Exception as e:
                    raise RuntimeError(f'Failed to load language {language}: {e}') from e

                avail_kernels = [
                    y.kernel
                    for y in self._kernel_list
                    if y.kernel in sum(plugin.supported_kernels.values(), []) or any(
                        fnmatch.fnmatch(y.kernel, x) for x in sum(plugin.supported_kernels.values(), []))
                ]

                if not avail_kernels:
                    raise ValueError(
                        'Failed to find any of the kernels {} supported by language {}. Please make sure it is properly installed and appear in the output of command "jupyter kenelspec list"'
                        .format(', '.join(sum(plugin.supported_kernels.values(), [])), language))
                # use the first available kernel
                # find the language that has the kernel
                lan_name = list({
                    x: y
                    for x, y in plugin.supported_kernels.items()
                    if avail_kernels[0] in y or any(fnmatch.fnmatch(avail_kernels[0], z) for z in y)
                }.keys())[0]
                if color == 'default':
                    color = self.get_background_color(plugin, lan_name)
                new_def = self.add_or_replace(
                    subkernel(
                        name,
                        avail_kernels[0],
                        lan_name,
                        self.get_background_color(plugin, lan_name) if color is None else color,
                        getattr(plugin, 'options', {}),
                        codemirror_mode=codemirror_mode))
            else:
                # if a language name is specified (not a path to module), if should be defined in setup.py
                if language not in self.language_info:
                    raise RuntimeError(f'Unrecognized language definition {language}')
                #
                plugin = self.language_info[language]
                if language in plugin.supported_kernels:
                    avail_kernels = [
                        y.kernel for y in self._kernel_list if y.kernel in plugin.supported_kernels[language] or any(
                            fnmatch.fnmatch(y.kernel, x) for x in plugin.supported_kernels[language])
                    ]
                else:
                    avail_kernels = [
                        y.kernel
                        for y in self._kernel_list
                        if y.kernel in sum(plugin.supported_kernels.values(), []) or any(
                            fnmatch.fnmatch(y.kernel, x) for x in sum(plugin.supported_kernels.values(), []))
                    ]
                if not avail_kernels:
                    raise ValueError(
                        'Failed to find any of the kernels {} supported by language {}. Please make sure it is properly installed and appear in the output of command "jupyter kenelspec list"'
                        .format(', '.join(sum(self.language_info[language].supported_kernels.values(), [])), language))

                new_def = self.add_or_replace(
                    subkernel(
                        name,
                        avail_kernels[0],
                        language,
                        self.get_background_color(self.language_info[language], language)
                        if color is None or color == 'default' else color,
                        getattr(self.language_info[language], 'options', {}),
                        codemirror_mode=codemirror_mode))

            self.notify_frontend()
            return new_def

        # let us check if there is something wrong with the pre-defined language
        for entrypoint in pkg_resources.entry_points(group='sos_languages'):
            if entrypoint.name == name:
                # there must be something wrong, let us trigger the exception here
                entrypoint.load()
        # if nothing is triggerred, kernel is not defined, return a general message
        raise ValueError(
            f'No subkernel named {name} is found. Please use magic "%use" without option to see a list of available kernels and language modules.'
        )

    def update(self, notebook_kernel_list):
        for kinfo in notebook_kernel_list:
            try:
                # if we can find the kernel, fine...
                self.find(
                    name=kinfo[0],
                    kernel=kinfo[1],
                    language=kinfo[2],
                    color=kinfo[3],
                    codemirror_mode='' if len(kinfo) >= 4 else kinfo[4],
                    notify_frontend=False)
            except Exception as e:
                # otherwise do not worry about it.
                env.logger.warning(
                    f'Failed to locate subkernel {kinfo[0]} with kernel "{kinfo[1]}" and language "{kinfo[2]}": {e}')

    def notify_frontend(self):
        self._kernel_list.sort(key=lambda x: x.name)
        self.sos_kernel.send_frontend_msg(
            'kernel-list',
            [[x.name, x.kernel, x.language, x.color, x.codemirror_mode, x.options] for x in self._kernel_list])
