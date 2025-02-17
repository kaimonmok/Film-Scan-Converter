import platform
import tkinter as tk
from tkinter import ttk
import logging
from typing import Callable, Iterable

logger = logging.getLogger(__name__)
FORMAT = '%(asctime)s:::%(levelname)s:::%(message)s'
logging.basicConfig(filename='logfile.log', level=logging.DEBUG, format=FORMAT)

class AutoScrollbar(ttk.Scrollbar):
   # A scrollbar that hides itself if it's not needed.
   # Only works if you use the grid geometry manager!
    def set(self, lo, hi):
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            # grid_remove is currently missing from Tkinter!
            self.tk.call('grid', 'remove', self)
        else:
            self.grid()
        ttk.Scrollbar.set(self, lo, hi)
    def pack(self, **kw):
        raise tk.TclError('cannot use pack with this widget')
    def place(self, **kw):
        raise tk.TclError('cannot use place with this widget')

class ScrollFrame:
    def __init__(self, master):
        self.vscrollbar = AutoScrollbar(master)
        self.vscrollbar.grid(row=0, column=1, sticky=tk.N+tk.S)
        self.hscrollbar = AutoScrollbar(master, orient=tk.HORIZONTAL)
        self.hscrollbar.grid(row=1, column=0, sticky=tk.E+tk.W)

        self.canvas = tk.Canvas(master, yscrollcommand=self.vscrollbar.set, xscrollcommand=self.hscrollbar.set, takefocus=0, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky='NSEW')

        self.vscrollbar.config(command=self.canvas.yview)
        self.hscrollbar.config(command=self.canvas.xview)

        # make the canvas expandable
        master.grid_rowconfigure(0, weight=1)
        master.grid_columnconfigure(0, weight=1)

        # create frame inside canvas
        self.frame = ttk.Frame(self.canvas)
        self.frame.rowconfigure(1, weight=1)
        self.frame.columnconfigure(1, weight=1)

        self.frame.bind('<Configure>', self.reset_scrollregion)
        self.frame.bind('<Enter>', lambda _: self.frame.bind_all('<MouseWheel>', self._on_mousewheel))
        self.frame.bind('<Leave>', lambda _: self.frame.unbind_all('<MouseWheel>'))

    def update(self):
        self.canvas.create_window(0, 0, anchor=tk.NW, window=self.frame)
        self.frame.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox('all'))

        if self.frame.winfo_reqwidth() != self.canvas.winfo_width():
            # update the canvas's width to fit the inner frame
            self.canvas.config(width = self.frame.winfo_reqwidth())
        if self.frame.winfo_reqheight() != self.canvas.winfo_height():
            # update the canvas's height to fit the inner frame
            self.canvas.config(height = self.frame.winfo_reqheight())
    
    def reset_scrollregion(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
    
    def _on_mousewheel(self, event):
        # binding mousewheel event to scrolling
        caller = event.widget
        if not (isinstance(caller, ttk.Spinbox) or isinstance(caller, ttk.Combobox)): # ignore scrolling on spinboxes and comboboxes
            if platform.system() == 'Windows': # setting different scrolling speeds based on platform
                delta_scale = 120
            else:
                delta_scale = 1
            if (self.frame.winfo_reqheight() > self.canvas.winfo_height()):
                self.canvas.yview_scroll(int(-1*(event.delta/delta_scale)), 'units')
    
class ScaleEntry:
    # Defines Label, Scale and Spinbox widgets, linked to a common integer or float variable
    # Has 4 methods that can be called: get(), set(), hide(), and show().
    # When the widget is interacted with, it will call the method passed into the command argument, and pass the widget itself as a parameter.
    def __init__(self, master, text: str, row: int, from_: int|float, to: int|float, key: str=None, widget_dictionary: dict=None, global_sync: bool=True, is_float=False, increment: int|float=1, default_value: int=0, command: Callable=lambda x:None):
        self.global_sync = global_sync
        self.row = row
        self.command = command
        self.key = key
        if widget_dictionary is not None and key is not None:
            widget_dictionary[self.key] = self

        def validate(input):
            # Validates if the input is numeric
            def set_value(value):
                # Function to replace value in current widget
                self.spinbox.delete(0,'end')
                self.spinbox.insert(0, value)
            if input == '' or input == '-':
                set_value(0)
            elif input == '0-':
                set_value('-0') # allows negative numbers to be more easily entered
            try:
                if is_float:
                    float(input)
                else:
                    int(input)
            except ValueError:
                return False # input is non-numeric
            else:
                # Get rid of leading zeros
                if input[:2] == '0.':
                    pass
                elif input[0] == '0' and len(input) > 1:
                    set_value(input[1:])
                elif (input[:2] == '-0') and (len(input) > 2):
                    if input[2] != '.':
                        set_value('-' + input[2:])
                return True

        validation = master.register(validate)

        # Building the widgets
        self.label = ttk.Label(master, text=text)
        if is_float:
            self.variable = tk.DoubleVar()
        else:
            self.variable = tk.IntVar()
        self.variable.set(default_value)
        self.scale = ttk.Scale(master, from_=from_, to=to, variable=self.variable, orient=tk.HORIZONTAL, value=self.variable.get(), length=100, command=lambda x:self.variable.set(round(float(x) / increment) * increment))
        self.scale.bind('<ButtonRelease-1>', lambda x: self.set(None, True))
        self.spinbox = ttk.Spinbox(master, from_=from_, to=to, increment=increment, textvariable=self.variable, command=lambda: self.set(None, True), width=5, validate='key', validatecommand=(validation, '%P'))
        self.spinbox.bind('<Return>', lambda x: self.set(None, True))
        self.spinbox.bind('<FocusOut>', lambda x: self.set(None, True))

        self.show()

    def get(self):
        # Returns the stored value
        return self.variable.get()

    def set(self, value=None, run_command=False):
        # Updates widgets to stored variable or value if given
        # set to run every time self.variable is updated
        # if triggered by an event (i.e. by changing the value manually through the GUI), executes self.command
        # with run_command, will always trigger self.command
        if type(value) is int or type(value) is float:
            self.variable.set(value)
        self.scale.set(self.variable.get())
        if run_command:
            self.command(self)

    def hide(self):
        # Hides the widget
        self.label.grid_forget()
        self.scale.grid_forget()
        self.spinbox.grid_forget()

    def show(self):
        # Shows the widget
        self.label.grid(row=self.row, column=0, sticky=tk.E)
        self.scale.grid(row=self.row, column=1, padx=2)
        self.spinbox.grid(row=self.row, column=2, sticky=tk.W)

class CheckLabel:
    # Defines Label, Checkbox widgets linked to a boolean variable
    # Has 6 methods that can be called: get(), set(), hide(), show(), enable() and disable().
    # When the widget is interacted with, it will call the method passed into the command argument, and pass the widget itself as a parameter.
    # Must be placed in grid
    def __init__(self, master, text: str, row: int, key: str=None, widget_dictionary: dict=None, global_sync: bool=True, default_value: bool=False, command: Callable=lambda x:None):
        self.global_sync = global_sync
        self.row = row
        self.key = key
        if widget_dictionary is not None and key is not None:
            widget_dictionary[self.key] = self # adding widget to provided dictionary

        # Building the widgets
        self.variable = tk.BooleanVar()
        self.variable.set(default_value)
        self.label = ttk.Label(master, text=text)
        self.checkbutton = ttk.Checkbutton(master, variable=self.variable, command=lambda: command(self))

        self.show()

    def get(self):
        # Returns the stored value
        return self.variable.get()

    def set(self, value: bool):
        # Updates checkbutton to provided boolean variable
        self.variable.set(value)

    def hide(self):
        # Hides the widget
        self.label.grid_forget()
        self.checkbutton.grid_forget()

    def show(self):
        # Shows the widget
        self.label.grid(row=self.row, column=0, sticky=tk.E)
        self.checkbutton.grid(row=self.row, column=1, sticky=tk.W)

    def enable(self):
        self.checkbutton.configure(state=tk.NORMAL)

    def disable(self):
        self.checkbutton.configure(state=tk.DISABLED)

class ComboLabel:
    # Defines Label, Checkbox widgets linked to a boolean variable
    # Has 6 methods that can be called: get(), set(), hide(), show(), enable() and disable().
    # When the widget is interacted with, it will call the method passed into the command argument, and pass the widget itself as a parameter.
    # Must be placed in grid
    def __init__(self, master, text: str, row: int, values: Iterable, key: str=None, widget_dictionary: dict=None, global_sync: bool=True, default_value: int=0, width: int=15, output_list: Iterable=[], command: Callable=lambda x:None):
        self.global_sync = global_sync
        self.row = row
        self.key = key
        self.output_list = output_list
        self.values = values
        if widget_dictionary is not None and key is not None:
            widget_dictionary[self.key] = self # adding widget to provided dictionary

        self.label = ttk.Label(master, text=text)
        self.combobox = ttk.Combobox(master, state='readonly', values=self.values, width=width-3)
        self.combobox.bind('<<ComboboxSelected>>', lambda x: command(self))
        self.set(default_value)
        self.show()
    
    def get(self, use_output_list: bool=True):
        # Returns the index of the combobox, or the corresponding element in output_list if given, and use_output_list = True
        if use_output_list and len(self.output_list) == len(self.values):
            # Returns the element of a list corresponding to the combobox
            return self.output_list[self.combobox.current()]
        else:
            # Returns the index of the combobox
            return self.combobox.current()

    def set(self, value):
        # if a valid output list is provided, will set the combobox to the item corresponding to the provided value,
        # otherwise, it will set the combobox using the provided value as an index
        if len(self.output_list) == len(self.values):
            if value in self.output_list:
                self.combobox.current(self.output_list.index(value)) # Sets the combobox to the actual value provided
            else:
                Exception('Provided value does not exist in list of values')
        else:
            self.combobox.current(value) # Sets combobox to the entry corresponding to provided index

    def hide(self):
        # Hides the widget
        self.label.grid_forget()
        self.combobox.grid_forget()

    def show(self):
        # Shows the widget
        self.label.grid(row=self.row, column=0, sticky=tk.E)
        self.combobox.grid(row=self.row, column=1, sticky=tk.W, padx=2, columnspan=2)

class MultiEntryLabel:
    # defines label with a given number of numerical entries
    # useful for when the modified parameter is an iterable
    # Has 4 methods that can be called: get(), set(), hide(), show().
    # When the widget is interacted with, it will call the method passed into the command argument, and pass the widget itself as a parameter.
    # Must be placed in grid
    def __init__(self, master, text: str, row: int, from_: int|float, to: int|float, num_entries: int, default_values: Iterable=None, key: str=None, widget_dictionary: dict=None, global_sync: bool=True, is_float=False, increment: int|float=1, width=20, command: Callable=lambda x:None):
        self.global_sync = global_sync
        self.row = row
        self.key = key
        if widget_dictionary is not None and key is not None:
            widget_dictionary[self.key] = self # adding widget to provided dictionary

        def validate(input, widget):
            # Validates if the input is numeric
            def set_value(value):
                # Function to replace value in current widget
                master.nametowidget(widget).delete(0,'end')
                master.nametowidget(widget).insert(0, value)
            if input == '' or input == '-':
                set_value(0)
            elif input == '0-':
                set_value('-0') # allows negative numbers to be more easily entered
            try:
                if is_float:
                    float(input)
                else:
                    int(input)
            except ValueError:
                return False # input is non-numeric
            else:
                # Get rid of leading zeros
                if input[:2] == '0.':
                    pass
                elif input[0] == '0' and len(input) > 1:
                    set_value(input[1:])
                elif (input[:2] == '-0') and (len(input) > 2):
                    if input[2] != '.':
                        set_value('-' + input[2:])
                return True
        
        def clamp(event=None):
            # clamps the variables between from_ and to
            for var in self.var_list:
                if var.get() > to:
                    var.set(to)
                elif var.get() < from_:
                    var.set(from_)
            command(self)

        validation = master.register(validate)

        self.label = ttk.Label(master, text=text)
        self.entry_frame = ttk.Frame(master)
        self.var_list = []
        column = 0
        entry_width = max(int(width / num_entries) - 2, 4) # calculating the width of each entry
        for _ in range(num_entries):
            if is_float:
                variable = tk.DoubleVar()
            else:
                variable = tk.IntVar()
            self.var_list.append(variable)
            spinbox = ttk.Spinbox(self.entry_frame, from_=from_, to=to, increment=increment, textvariable=variable, command=clamp, width=entry_width, validate='key', validatecommand=(validation, '%P', '%W'))
            spinbox.grid(row=self.row, column=column)
            spinbox.bind('<Return>', clamp)
            spinbox.bind('<FocusOut>', clamp)
            column += 1

        if default_values is not None:
            self.set(default_values)
        self.show()

    def get(self):
        # Returns the stored value as either a tuple or a single value if there is only one entry
        output = tuple([var.get() for var in self.var_list])
        if len(output) == 1:
            return output[0]
        else:
            return output

    def set(self, values: int|float|Iterable):
        # Updates widgets to stored variable or value if given
        # length of input must match number of entries
        if type(values) is int or type(values) is float:
            values = [values]
        if len(values) != len(self.var_list):
            Exception('Length of input does not equal number of entries')
        for value, var in zip(values, self.var_list):
            var.set(value)

    def hide(self):
        # Hides the widget
        self.label.grid_forget()
        self.entry_frame.grid_forget()

    def show(self):
        # Shows the widget
        self.label.grid(row=self.row, column=0, sticky=tk.E)
        self.entry_frame.grid(row=self.row, column=1, sticky='new', padx=2, pady=2)