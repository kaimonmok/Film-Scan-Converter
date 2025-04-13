import os
import psutil
import sys
from tkinter import ttk,  filedialog, messagebox, colorchooser
import tkinter as tk
from PIL import ImageTk
import threading
import numpy as np 
import cv2
import multiprocessing
from typing import Literal

#custom classes
from CustomWidgets import ScrollFrame, ScaleEntry, CheckLabel, ComboLabel, EntryLabel, MultiEntryLabel
from RawProcessing import RawProcessing

#logging
import logging

logger = logging.getLogger(__name__)
FORMAT = '%(asctime)s:::%(levelname)s:::%(message)s'
logging.basicConfig(filename='logfile.log', level=logging.DEBUG, format=FORMAT)

class GUI:
    def __init__(self, master):
        # Initialize Variables
        self.config_path = self._check_and_create_conf_folder()
        self.photos = []
        self.in_progress = set() # keeps track photos that are in processing when first loading
        self.photo_process_values = ['RAW', 'Threshold', 'Contours', 'Histogram', 'Full Preview']
        self.filetypes = ['TIFF', 'PNG', 'JPG'] # Export File Types
        self.fit_aspect_ratios = ['Keep Original', '16:9 (Landscape)', '3:2 (Landscape)', '4:3 (Landscape)', '5:4 (Landscape)', '1:1 (Square)', '4:5 (Portrait)', '3:4 (Portrait)', '2:3 (Portrait)', '9:16 (Portrait)']
        self.destination_folder = ''
        self.allowable_image_filetypes = [
            ('RAW files', '*.DNG *.CR2 *.CR3 *.NEF *.ARW *.RAF *.ERF *.GPR *.RAW *.CRW *.dng *.cr2 *.cr3 *.nef *.arw *.raf *.erf *.grp *.raw *.crw'),
            ('Image files', '*.PNG *.JPG *.JPEG *.BMP *.TIFF *.TIF *.png *.jpg *.jpeg *.bmp *.tiff *.tif')
            ]
        self.header_style = ('Segoe UI', 10, 'normal') # Defines font for section headers
        self.wb_picker = False
        self.base_picker = False
        self.unsaved = False # Indicates that settings have changed need to be saved

        self.default_advanced_settings = dict(
            max_processors_override = 0, # 0 means disabled
            preload = 4 # Buffer size to preload photos
        )
        self.advanced_settings = self.default_advanced_settings.copy()

        self.default_settings = dict(
            film_type = 0,
            dark_threshold = 25,
            light_threshold = 100,
            border_crop = 1,
            flip = False,
            white_point = 0,
            black_point = 0,
            gamma = 0,
            shadows = 0,
            highlights = 0,
            temp = 0,
            tint = 0,
            sat = 100,
            base_detect = 0,
            base_rgb = (255, 255, 255),
            remove_dust = False
        )

        self.global_settings = self.default_settings.copy()
        self.master = master
        # Building the GUI
        self.master.title('Film Scan Converter')
        try:
            self.master.state('zoomed')
        except Exception as e: # Exception for linux
            m = self.master.maxsize()
            self.master.geometry('{}x{}+0+0'.format(*m))
            logger.exception(f'Exception: {e}')
        self.master.geometry('800x500')

        menubar = tk.Menu(self.master, relief=tk.FLAT)
        self.filemenu = tk.Menu(menubar, tearoff=0)
        self.filemenu.add_command(label='Import...', command=self.import_photos)
        self.filemenu.add_command(label='Save Settings', command=self.save_settings, accelerator='Ctrl+S')
        self.filemenu.add_separator()
        self.filemenu.add_command(label='Exit', command=self.on_closing)
        menubar.add_cascade(label='File', menu=self.filemenu)
        self.editmenu = tk.Menu(menubar, tearoff=0)
        self.editmenu.add_command(label='Copy Settings', command=self.copy_settings, accelerator='Ctrl+C')
        self.editmenu.add_command(label='Paste Settings', command=self.paste_settings, state=tk.DISABLED, accelerator='Ctrl+V')
        self.editmenu.add_separator()
        self.editmenu.add_command(label='Reset to Default Settings', command=self.reset_settings)
        self.editmenu.add_separator()
        self.editmenu.add_command(label='Advanced Settings...', command=self.advanced_dialog)
        self.editmenu.add_command(label='Add EXIF data', command=self.add_exifdata)
        menubar.add_cascade(label='Edit', menu=self.editmenu)
        self.master.config(menu=menubar)

        mainFrame = ttk.Frame(self.master, padding=10)
        mainFrame.pack(side=tk.TOP, anchor=tk.NW, fill='both', expand=True)
        mainFrame.grid_rowconfigure(0, weight=1)
        mainFrame.grid_columnconfigure(1, weight=1)

        self.controlsFrame = ttk.Frame(mainFrame)
        self.controlsFrame.grid(row=0, column=0, sticky='NS', rowspan=10)
        self.controlsFrame.grid_rowconfigure(0, weight=1)
        self.controlsFrame.grid_columnconfigure(0, weight=1)
        dynamic_scroll_frame = ScrollFrame(self.controlsFrame)

        self.widgets = {} # stores dictionary of all widgets

        # Importing RAW scans
        import_title = ttk.Label(text='Select Photo', font=self.header_style, padding=2)
        importFrame = ttk.LabelFrame(dynamic_scroll_frame.frame, borderwidth=2, labelwidget=import_title, padding=5)
        importFrame.grid(row=0, column=0, sticky='EW')
        importSubFrame1 = ttk.Frame(importFrame)
        importSubFrame1.pack(fill='x')
        ttk.Label(importSubFrame1, text='RAW File:').pack(side=tk.LEFT)
        self.photoCombo = ttk.Combobox(importSubFrame1, state='readonly')
        self.photoCombo.bind('<<ComboboxSelected>>', self.load_IMG)
        self.photoCombo.pack(side=tk.LEFT, padx=2)
        self.import_button = ttk.Button(importSubFrame1, text='Import...', command=self.import_photos, width=8)
        self.import_button.pack(side=tk.LEFT, padx=2)
        importSubFrame2 = ttk.Frame(importFrame)
        importSubFrame2.pack(fill='x')
        self.prevButton = ttk.Button(importSubFrame2, text='< Previous Photo', width=20, command=self.previous)
        self.prevButton.pack(side=tk.LEFT, padx=2, pady=5)
        self.set_tooltip(self.prevButton, "(Left Arrow)")
        self.nextButton = ttk.Button(importSubFrame2, text='Next Photo >', width=20, command=self.next)
        self.nextButton.pack(side=tk.LEFT, padx=2, pady=5)
        self.set_tooltip(self.nextButton, "(Right Arrow)")

        # Processing Frame
        processing_title = ttk.Label(text='Processing Settings', font=self.header_style, padding=2)
        processingFrame = ttk.LabelFrame(dynamic_scroll_frame.frame, borderwidth=2, labelwidget=processing_title, padding=5)
        processingFrame.grid(row=1, column=0, sticky='EW')
        # Reject Checkbutton to exclude from export
        rejectFrame = ttk.Frame(processingFrame)
        rejectFrame.grid(row=0, column=0, sticky='EW')
        self.reject_check = CheckLabel(rejectFrame, 'Reject Photo:', 0, 'reject', self.widgets, False, command=lambda widget: self.widget_changed(widget, 'update'))
        # Selection of global settings
        self.globFrame = ttk.Frame(processingFrame)
        self.globFrame.grid(row=1, column=0, sticky='EW')
        self.glob_check = CheckLabel(self.globFrame, 'Sync with Global Settings:', 0, default_value=True, global_sync=False, command=self.set_global)
        # Selection of film type
        self.filmFrame = ttk.Frame(processingFrame)
        self.filmFrame.grid(row=3, column=0, sticky='EW')
        film_types = ['Black & White Negative', 'Colour Negative', 'Slide (Colour Positive)','Crop Only (RAW)']
        self.film_type = ComboLabel(self.filmFrame, 'Film Type:', 0, film_types, 'film_type', self.widgets, width=25, command=self.widget_changed)
        # Dust removal
        self.dustFrame = ttk.Frame(processingFrame)
        self.dustFrame.grid(row=4, column=0, sticky='EW')
        CheckLabel(self.dustFrame, 'Remove Dust:', 0, 'remove_dust', self.widgets, command=lambda widget: self.widget_changed(widget, 'update'))

        # Automatic Cropping Settings
        controls_title = ttk.Label(text='Automatic Crop & Rotate', font=self.header_style, padding=2)
        self.cropFrame = ttk.LabelFrame(dynamic_scroll_frame.frame, borderwidth=2, labelwidget=controls_title, padding=5)
        self.cropFrame.grid(row=4, column=0, sticky='EW')
        crop_adjustments = ttk.Frame(self.cropFrame)
        crop_adjustments.pack(fill='x')
        crop_adjustments.grid_rowconfigure(1, weight=1)
        crop_adjustments.grid_columnconfigure(3, weight=1)
        ScaleEntry(crop_adjustments, 'Dark Threshold:', 0, 0, 100, 'dark_threshold', self.widgets, command=self.widget_changed)
        ScaleEntry(crop_adjustments, 'Light Threshold:', 1, 0, 100, 'light_threshold', self.widgets, command=self.widget_changed)
        ScaleEntry(crop_adjustments, 'Border Crop (%):', 2, -5, 20, 'border_crop', self.widgets, command=self.widget_changed)
        self.flip_check = CheckLabel(crop_adjustments, 'Flip Horizontally:', 3, 'flip', self.widgets, command=self.set_flip)
        rotButtons = ttk.Frame(self.cropFrame)
        rotButtons.pack(fill='x')
        ttk.Button(rotButtons, text='Rotate Counterclockwise', width=22, command=self.rot_counterclockwise).pack(side=tk.LEFT, padx=2, pady=5)
        self.set_tooltip(rotButtons.winfo_children()[-1], "(Shift+R)")
        ttk.Button(rotButtons, text='Rotate Clockwise', width=22, command=self.rot_clockwise).pack(side=tk.LEFT, padx=2, pady=5)
        self.set_tooltip(rotButtons.winfo_children()[-1], "(R)")

        # Colour settings
        if getattr(sys, 'frozen', False):
            picker = tk.PhotoImage(file=os.path.join(sys._MEIPASS, 'dropper.png')).subsample(15,15)
        else:
            picker = tk.PhotoImage(file=os.path.join('assets', 'dropper.png')).subsample(15,15)
        colour_title = ttk.Label(text='Colour Adjustment', font=self.header_style, padding=2)
        self.colourFrame = ttk.LabelFrame(dynamic_scroll_frame.frame, borderwidth=2, labelwidget=colour_title, padding=5)
        colour_controls = ttk.Frame(self.colourFrame)
        colour_controls.pack(fill='x', side=tk.LEFT)
        base_setting_modes = ['Auto Detect','Set Manually']
        self.base_mode = ComboLabel(colour_controls, 'Film Base Colour', 0, base_setting_modes, 'base_detect', self.widgets, command=self.set_base_detect)
        self.base_clr_lbl = ttk.Label(colour_controls, text='RGB:')
        self.base_rgb = tk.StringVar()
        self.base_rgb.set(str(self.global_settings['base_rgb']))
        self.base_rgb_lbl = ttk.Label(colour_controls, textvariable=self.base_rgb)
        self.rgb_display = tk.Frame(colour_controls, bg=self._from_rgb(self.global_settings['base_rgb']), height=20, width=20, relief=tk.GROOVE, borderwidth=1)
        self.base_pick_button = ttk.Button(colour_controls, image=picker, command=self.set_base)
        self.base_pick_button.image = picker
        self.base_buttons_frame = ttk.Frame(colour_controls)
        ttk.Button(self.base_buttons_frame, text='Set RGB', command=lambda:self.set_base_rgb(0), width=8).pack(side=tk.LEFT, padx=2, pady=2, anchor='center')
        ttk.Button(self.base_buttons_frame, text='Import Blank...', command=lambda:self.set_base_rgb(2), width=13).pack(side=tk.LEFT, padx=2, pady=2, anchor='center')
        ttk.Label(colour_controls, text='White Balance Picker:').grid(row=3, column=0, sticky=tk.E)
        self.wb_picker_button = ttk.Button(colour_controls, image=picker, command=self.pick_wb)
        self.wb_picker_button.grid(row=3, column=1, sticky=tk.W)
        self.wb_picker_button.image = picker
        self.temp = ScaleEntry(colour_controls, 'Temperature:', 4, -100, 100, 'temp', self.widgets, increment=1, command=lambda widget:self.widget_changed(widget, 'skip crop'))
        self.tint = ScaleEntry(colour_controls, 'Tint:', 5, -100, 100, 'tint', self.widgets, increment=1, command=lambda widget:self.widget_changed(widget, 'skip crop'))
        ScaleEntry(colour_controls, 'Saturation (%):', 6, 0, 200, 'sat', self.widgets, increment=10, command=lambda widget:self.widget_changed(widget, 'skip crop'))
        
        # Brightness Settings
        brightness_title = ttk.Label(text='Brightness Adjustment', font=self.header_style, padding=2)
        self.exposureFrame = ttk.LabelFrame(dynamic_scroll_frame.frame, borderwidth=2, labelwidget=brightness_title, padding=5)
        self.exposureFrame.grid(row=7, column=0, sticky='EW')
        exposureControls = ttk.Frame(self.exposureFrame)
        exposureControls.pack(fill='x', side=tk.LEFT)
        exposureControls.grid_rowconfigure(6, weight=1)
        exposureControls.grid_columnconfigure(3, weight=1)
        ScaleEntry(exposureControls, 'White Point:', 0, -100, 100, 'white_point', self.widgets, increment=5, command=lambda widget:self.widget_changed(widget, 'skip crop'))
        ScaleEntry(exposureControls, 'Black Point:', 1, -100, 100, 'black_point', self.widgets, increment=5, command=lambda widget:self.widget_changed(widget, 'skip crop'))
        ScaleEntry(exposureControls, 'Gamma:', 2, -100, 100, 'gamma', self.widgets, increment=5, command=lambda widget:self.widget_changed(widget, 'skip crop'))
        ScaleEntry(exposureControls, 'Shadows:', 3, -100, 100, 'shadows', self.widgets, increment=5, command=lambda widget:self.widget_changed(widget, 'skip crop'))
        ScaleEntry(exposureControls, 'Highlights:', 4, -100, 100, 'highlights', self.widgets, increment=5, command=lambda widget:self.widget_changed(widget, 'skip crop'))

        # Export photo settings
        export_title = ttk.Label(text='Export Settings', font=self.header_style, padding=2)
        export_frame = ttk.LabelFrame(dynamic_scroll_frame.frame, borderwidth=2, labelwidget=export_title, padding=5)
        export_frame.grid(row=9, column=0, sticky='EW')
        export_settings_frame = ttk.Frame(export_frame)
        export_settings_frame.pack(fill='x')
        ComboLabel(export_settings_frame, 'Export File Type:', 0, self.filetypes, 'filetype', global_sync=False, output_list=self.filetypes, command=lambda widget:self.widget_changed(widget, 'skip', False), default_value=RawProcessing.default_parameters['filetype'])
        self.frame = ScaleEntry(export_settings_frame, 'White Frame (%):', 1, 0, 10, 'frame', global_sync=False, command=lambda widget:self.widget_changed(widget, 'update', False), default_value=RawProcessing.default_parameters['frame'])
        ComboLabel(export_settings_frame, 'Fit Aspect Ratio:', 2, self.fit_aspect_ratios, 'fit_aspect_ratio', global_sync=False, output_list=self.fit_aspect_ratios, command=lambda widget:self.widget_changed(widget, 'update', False), default_value=RawProcessing.default_parameters['fit_aspect_ratio'], width=20)
        export_settings_frame.pack(fill='x', pady=(0, 15)) # adds some spacing
        
        ttk.Label(export_frame, text='Output Destination Folder:', anchor='w').pack(fill = 'x')
        self.destination_folder_text = tk.StringVar()
        self.destination_folder_text.set('No Destination Folder Specified')
        destination_lbl = ttk.Label(export_frame, textvariable=self.destination_folder_text, anchor='w', font=('Segoe UI', 9, 'italic'))
        destination_lbl.pack(fill = 'x')
        destination_lbl.bind('<Configure>', lambda e: destination_lbl.config(wraplength=destination_lbl.winfo_width()))
        ttk.Button(export_frame, text='Select Folder', command=self.select_folder).pack(side=tk.LEFT, padx=2, pady=5)
        self.current_photo_button = ttk.Button(export_frame, text='Export Current Photo', command=self.export, state=tk.DISABLED)
        self.current_photo_button.pack(side=tk.LEFT, padx=2, pady=5)
        self.all_photo_button = ttk.Button(export_frame, text='Export All Photos', command=lambda: self.export(len(self.photos)), state=tk.DISABLED)
        self.all_photo_button.pack(side=tk.LEFT, padx=2, pady=5)
        self.abort_button = ttk.Button(export_frame, text='Abort Export', command=self.abort)

        # Progress Bar
        self.progressFrame = ttk.Frame(self.controlsFrame, padding=2)
        self.progress_percentage = ttk.Label(self.progressFrame)
        self.progress_percentage.pack(side=tk.RIGHT, anchor='n')
        self.progress = tk.DoubleVar()
        self.progress.set(0)
        self.progress_bar = ttk.Progressbar(self.progressFrame, variable=self.progress)
        self.progress_bar.pack(fill='x')
        self.progress_msg = ttk.Label(self.progressFrame)
        self.progress_msg.pack(side=tk.LEFT)

        # Showing converted image preview and intermediary steps
        self.outputFrame = ttk.Frame(mainFrame)
        self.outputFrame.grid_rowconfigure(3, weight=1)
        self.outputFrame.grid_columnconfigure(0, weight=1)
        self.read_error_lbl = ttk.Label(mainFrame, text='Error: File could not be read', font=('Segoe UI', 20), justify='center', anchor='center')
        self.read_error_lbl.bind('<Configure>', lambda e: self.read_error_lbl.config(wraplength=self.read_error_lbl.winfo_width()))

        # Process showing
        process_select_Frame = ttk.Frame(self.outputFrame)
        process_select_Frame.grid(row=0, column=0, pady=3)
        process_select_Frame.grid_rowconfigure(0, weight=1)
        process_select_Frame.grid_columnconfigure(1, weight=1)
        ttk.Label(process_select_Frame, text='Show:').grid(row=0, column=0)
        self.photo_process_Combo = ttk.Combobox(process_select_Frame, state='readonly', values=self.photo_process_values)
        self.photo_process_Combo.current(0)
        self.photo_process_Combo.bind('<<ComboboxSelected>>', self.update_IMG)
        self.photo_process_Combo.grid(row=0, column=1, padx=2)
        self.set_tooltip(self.photo_process_Combo, "(Q) RAW\n(W) Threshold\n(E) Contours\n(H) Histogram\n(F) Full Preview")
        self.process_photo_frame = tk.Frame(self.outputFrame, padx=3, pady=3)
        self.process_photo_frame.grid(row=1, column=0)
        self.process_photo = ttk.Label(self.process_photo_frame)
        self.process_photo.pack()

        # Converted Preview
        ttk.Label(self.outputFrame, text='Preview:', font=self.header_style).grid(row=2, column=0)
        self.result_photo_frame = tk.Frame(self.outputFrame, padx=3, pady=3)
        self.result_photo_frame.grid(row=3, column=0)
        self.result_photo = ttk.Label(self.result_photo_frame)
        self.result_photo.pack()

        # Bindings
        self.master.bind('<Configure>', self.resize_event)
        self.master.bind('<Key>', self.key_handler)
        self.master.bind('<Button>', self.click)
        self.master.bind('<Control-c>', self.copy_settings)
        self.master.bind('<Control-v>', self.paste_settings)
        self.master.bind('<Control-s>', self.save_settings)
        self.master.protocol('WM_DELETE_WINDOW', self.on_closing)

        dynamic_scroll_frame.update()
        self.set_disable_buttons()

        # Loading advanced parameters from the config file
        try:
            params_dict = np.load(os.path.join(self.config_path,'config.npy'), allow_pickle=True).item()
        except Exception as e:
            logger.exception(f'Exception: {e}')
        else:
            for settings in [self.advanced_settings, RawProcessing.class_parameters]:
                for attr in settings:
                    if attr in params_dict:
                        settings[attr] = params_dict[attr] # Initializes every parameter with imported parameters
                    else:
                        logger.exception(f'Attribute {attr} not found in imported config.npy file.')
                    
        for widget in self.widgets.values():
            if widget.key in self.default_settings:
                widget.set(self.default_settings[widget.key]) # initializes widgets with default settings
    
    def _check_and_create_conf_folder(self) -> str:
        '''
        Check if conf folder exists and, if not, it creates it

        Returns: 
            The folder's path
        '''
      
        folder_path = os.path.join(os.path.expanduser('~'), '.film_scan_converter')
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            logger.info(f'Creating {folder_path} folder')
        return folder_path

    def advanced_dialog(self):
        # Pop-up window to contain all the advanced settings that don't fit in the main controls
        def set_wb(event=None):
            # Hides or shows wb multipliers if using wb from camera
            if use_camera_wb.get():
                wb_mult.hide()
            else:
                wb_mult.show()

        def apply_settings():
            # applies the values stored in the widgets to the rest of the class
            for widget in advanced_widgets.values():
                if widget.key in RawProcessing.class_parameters:
                    RawProcessing.class_parameters[widget.key] = widget.get()
                else:
                    self.advanced_settings[widget.key] = widget.get()
            
            quit()
            for photo in self.photos:
                photo.clear_memory()
            self.load_IMG()
        
        def save_settings():
            # saves the advanced settings as a config.npy file
            apply_settings()
            params_dict = dict()
            for attr in RawProcessing.advanced_attrs:
                params_dict[attr] = RawProcessing.class_parameters[attr]
            for attr in self.advanced_settings:
                params_dict[attr] = self.advanced_settings[attr]
            np.save(f'{os.path.join(self.config_path,"config.npy")}', params_dict)
        
        def quit():
            self.master.attributes('-topmost', 0)
            top.destroy()

        def set_widgets(settings_dict):
            # Applies the settings stored in the settings_dict to the advanced GUI
            for widget in advanced_widgets.values():
                if widget.key in settings_dict:
                    widget.set(settings_dict[widget.key])
        
        def reset():
            # Resets advanced settings to default values
            set_widgets(RawProcessing.default_parameters)
            set_widgets(self.default_advanced_settings)
            set_wb()

        top = tk.Toplevel(self.master)
        top.transient(self.master)
        top.title('Advanced Settings')
        top.grab_set()
        top.bind('<Button>', lambda event: event.widget.focus_set())
        top.resizable(False, False)
        top.focus_set()
        top.protocol('WM_DELETE_WINDOW', quit)

        mainFrame = ttk.Frame(top, padding=10)
        mainFrame.pack(fill='x')
        firstColumn = ttk.Frame(mainFrame, padding=2)
        firstColumn.grid(row=0, column=0, sticky='n')
        import_lbl = ttk.Label(top, text='Import:', font=self.header_style, padding=2)
        import_settings = ttk.LabelFrame(firstColumn, borderwidth=2, labelwidget=import_lbl, padding=5)
        import_settings.pack(fill='x', expand=True)
        export_lbl = ttk.Label(top, text='Export:', font=self.header_style, padding=2)
        export_settings = ttk.LabelFrame(firstColumn, borderwidth=2, labelwidget=export_lbl, padding=5)
        export_settings.pack(fill='x', expand=True)
        secondColumn = ttk.Frame(mainFrame, padding=2)
        secondColumn.grid(row=0, column=1, sticky='n')
        process_lbl = ttk.Label(top, text='Processing:', font=self.header_style, padding=2)
        process_settings = ttk.LabelFrame(secondColumn, borderwidth=2, labelwidget=process_lbl, padding=5)
        process_settings.pack(fill='x', expand=True)
        dust_lbl = ttk.Label(top, text='Dust Removal:', font=self.header_style, padding=2)
        dust_settings = ttk.LabelFrame(secondColumn, borderwidth=2, labelwidget=dust_lbl, padding=5)
        dust_settings.pack(fill='x', expand=True)

        advanced_widgets = {}

        # Building pop-up GUI
        allowable_dm_algs = (0, 1, 2, 3, 4, 11, 12)
        dm_algs_list = ('LINEAR','VNG','PPG','AHD','DCB','DHT','AAHD')
        ComboLabel(import_settings, 'Demosaicing Algorithm:', 0, dm_algs_list, 'dm_alg', advanced_widgets, output_list=allowable_dm_algs, width=25)
        MultiEntryLabel(import_settings, 'Median Filter Passes:', 1, 0, 10, 1, key='median_filter_passes', widget_dictionary=advanced_widgets, width=25)
        cs_list = ('raw','sRGB','Adobe','Wide','ProPhoto','XYZ','ACES','P3D65','Rec2020')
        ComboLabel(import_settings, 'RAW Output Colour Space:', 2, cs_list, 'colour_space', advanced_widgets, width=25)
        MultiEntryLabel(import_settings, 'RAW Gamma (Power, Slope):', 3, 0, 8, 2, key='raw_gamma', widget_dictionary=advanced_widgets, is_float=True, increment=0.1, width=25)
        MultiEntryLabel(import_settings, 'RAW Exposure Shift:', 4, -2, 3, 1, key='exp_shift', widget_dictionary=advanced_widgets, is_float=True, increment=0.25, width=25)
        fbdd_nr_list = ('Off','Light','Full')
        ComboLabel(import_settings, 'FBDD Noise Reduction:', 5, fbdd_nr_list, 'fbdd_nr', advanced_widgets, width=25)
        MultiEntryLabel(import_settings, 'Noise Threshold', 6, 0, 1000, 1, key='noise_thr', widget_dictionary=advanced_widgets, increment=50, width=25)
        use_camera_wb = CheckLabel(import_settings, 'Use Camera White Balance:', 8, 'use_camera_wb', advanced_widgets, command=set_wb)
        try:
            wb_lbl = f'White Balance Multipliers ({self.current_photo.colour_desc}):'
        except Exception as e:
            wb_lbl = 'White Balance Multipliers:'
        wb_mult = MultiEntryLabel(import_settings, wb_lbl, 9, 0, 4, 4, key='wb_mult', widget_dictionary=advanced_widgets, is_float=True, increment=0.1, width=25)

        MultiEntryLabel(process_settings, 'Max Proxy Size (W + H):', 0, 500, 20000, 1, key='max_proxy_size', widget_dictionary=advanced_widgets, increment=500)
        MultiEntryLabel(process_settings, 'Photo Preload Buffer Size:', 1, 0, 20, 1, key='preload', widget_dictionary=advanced_widgets)
        MultiEntryLabel(process_settings, 'EQ Ignore Borders % (W, H)', 2, 0, 40, 2, key='ignore_border', widget_dictionary=advanced_widgets)
        CheckLabel(process_settings, 'EQ Ignore Negative Borders:', 3, 'ignore_neg_border', advanced_widgets, default_value=True)
        MultiEntryLabel(process_settings, 'White Point Percentile:', 4, 70, 100, 1, key='white_point_percentile', widget_dictionary=advanced_widgets, is_float=True)
        MultiEntryLabel(process_settings, 'Black Point Percentile:', 5, 0, 30, 1, key='black_point_percentile', widget_dictionary=advanced_widgets, is_float=True)
        MultiEntryLabel(process_settings, 'Colour Picker Radius (%)', 6, 0.5, 10, 1, key='picker_radius', widget_dictionary=advanced_widgets, is_float=True, increment=0.5)

        MultiEntryLabel(dust_settings, 'Threshold:', 0, 0, 50, 1, key='dust_threshold', widget_dictionary=advanced_widgets)
        MultiEntryLabel(dust_settings, 'Noise Closing Iterations:', 1, 1, 10, 1, key='dust_iter', widget_dictionary=advanced_widgets)
        MultiEntryLabel(dust_settings, 'Max Particle Area:', 2, 0, 100, 1, key='max_dust_area', widget_dictionary=advanced_widgets)

        MultiEntryLabel(export_settings, 'JPEG Quality:', 0, 0, 100, 1, key='jpg_quality', widget_dictionary=advanced_widgets, increment=10)
        tiff_comp_list = ['No Compression','Lempel-Ziv & Welch','Adobe Deflate (ZIP)','PackBits']
        tiff_comp_out = [1, 5, 8, 32773]
        ComboLabel(export_settings, 'TIFF Compression:', 1, tiff_comp_list, 'tiff_compression', advanced_widgets, False, output_list=tiff_comp_out, width=20)
        MultiEntryLabel(export_settings, 'Max Processors Override:', 2, 0, multiprocessing.cpu_count(), 1, key='max_processors_override', widget_dictionary=advanced_widgets)

        set_widgets(RawProcessing.class_parameters)
        set_widgets(self.advanced_settings)
        set_wb()

        buttonFrame = ttk.Frame(mainFrame)
        buttonFrame.grid(row=1, column=0, columnspan=2, sticky='e')
        ttk.Button(buttonFrame, text='Cancel', command=quit).pack(side=tk.RIGHT, padx=2, pady=5, anchor='sw')
        ttk.Button(buttonFrame, text='Save', command=save_settings).pack(side=tk.RIGHT, padx=2, pady=5, anchor='sw')
        ttk.Button(buttonFrame, text='Reset to Default', command=reset, width=17).pack(side=tk.RIGHT, padx=2, pady=5, anchor='sw')

        # Centres pop-up window over self.master window
        top.update_idletasks()
        x = self.master.winfo_x() + int((self.master.winfo_width()/2) - (top.winfo_width()/2))
        y = self.master.winfo_y() + int((self.master.winfo_height()/2) - (top.winfo_height()/2))
        top.geometry('+%d+%d' % (x, y))

    def add_exifdata(self):
        def save_settings():
            # applies the values stored in the widgets to raw processing
            for widget in widget_dict.values():
                if widget.key in RawProcessing.exif_parameters:
                    RawProcessing.exif_parameters[widget.key] = widget.get()
            
            quit()
            

        def quit():
            self.master.attributes('-topmost', 0)
            top.destroy()

        top = tk.Toplevel(self.master)
        top.transient(self.master)
        top.title('Add EXIF data')
        top.grab_set()
        top.bind('<Button>', lambda event: event.widget.focus_set())
        top.resizable(False, False)
        top.focus_set()
        top.protocol('WM_DELETE_WINDOW', quit)

        mainFrame = ttk.Frame(top, padding=10)
        mainFrame.pack(fill='x')

        firstColumn = ttk.Frame(mainFrame, padding=2)
        firstColumn.grid(row=0, column=0, sticky='n')

        widget_dict = {}
        
        label_camera_information = ttk.Label(top, text='Camera Information', font=self.header_style, padding=2)
        labelframe_camera_information = ttk.LabelFrame(firstColumn, borderwidth=2, labelwidget=label_camera_information, padding=5)
        labelframe_camera_information.pack(fill='x', expand=True)

        EntryLabel(labelframe_camera_information, 'Camera make', 0, 'camera_make', widget_dict)
        EntryLabel(labelframe_camera_information, 'Camera model', 1, 'camera_model', widget_dict)

        label_lens_information = ttk.Label(top, text='Lens Information', font=self.header_style, padding=2)
        labelframe_lens_information = ttk.LabelFrame(firstColumn, borderwidth=2, labelwidget=label_lens_information, padding=5)
        labelframe_lens_information.pack(fill='x', expand=True)

        EntryLabel(labelframe_lens_information, 'Lens make', 0, 'lens_make', widget_dict)
        EntryLabel(labelframe_lens_information, 'Lens model', 1, 'lens_model', widget_dict)

        label_datetime_information = ttk.Label(top, text='Date and Time', font=self.header_style, padding=2)
        labelframe_datetime_information = ttk.LabelFrame(firstColumn, borderwidth=2, labelwidget=label_datetime_information, padding=5)
        labelframe_datetime_information.pack(fill='x', expand=True)

        EntryLabel(labelframe_datetime_information, 'Date Time Original', 0, 'date_time_original', widget_dict, 'YYYY:MM:DD hh:mm:ss')

        buttonFrame = ttk.Frame(mainFrame)
        buttonFrame.grid(row=1, column=0, columnspan=2, sticky='e')
        ttk.Button(buttonFrame, text='Save', command=save_settings).pack(side=tk.LEFT, padx=2, pady=5, anchor='sw')

        # Centres pop-up window over self.master window
        top.update_idletasks()
        x = self.master.winfo_x() + int((self.master.winfo_width()/2) - (top.winfo_width()/2))
        y = self.master.winfo_y() + int((self.master.winfo_height()/2) - (top.winfo_height()/2))
        top.geometry('+%d+%d' % (x, y))

    def widget_changed(self, widget, mode: Literal['normal','skip crop','update','skip']='normal', instance=True):
        # called whenever widget is changed
        # applies value stored in widget to photo
        # mode: some setting changes don't need to fully reprocess the photo, this speeds up processing
        # instance: whether the variable is changing an instance variable or class variable
        value = widget.get()
        key = widget.key
        if self.glob_check.get() and widget.global_sync:
            self.global_settings[key] = value
            self.changed_global_settings()
        self.update_UI()
        if instance:
            if hasattr(self, 'current_photo'):
                setattr(self.current_photo, key, value) # change instance
        else:
            RawProcessing.class_parameters[key] = value
        if len(self.photos) == 0:
            return
        match mode:
            case 'normal':
                self.current_photo.process()
                self.update_IMG()
                self.unsaved = True
            case 'skip crop':
                self.current_photo.process(skip_crop=True)
                self.update_IMG()
                self.unsaved = True
            case 'update':
                self.update_IMG()
                self.unsaved = True
            case 'skip':
                pass
    
    def import_photos(self):
        # Import photos: opens dialog to load files, and intializes GUI
        if len(self.photos) > 0:
            if self.ask_save_settings() is None:
                return
            
        if hasattr(self, 'export_thread') and self.export_thread.is_alive():
            return # don't run if the export is running
            
        filenames = filedialog.askopenfilenames(title='Select RAW File(s)', filetypes=self.allowable_image_filetypes) # show an 'Open' dialog box and return the path to the selected files
        if len(filenames) == 0:
            return # if user clicks 'cancel', abort operation
        
        self.show_progress('Initializing import...') # display progress opening
        self.import_button.configure(state=tk.DISABLED)
        self.filemenu.entryconfigure('Import...', state=tk.DISABLED)
        
        total = len(filenames)
        self.photos = []
        photo_names = []
        
        self.update_progress(20, f'Initializing {str(total)} photos...')
        for i, filename in enumerate(filenames):
            photo = RawProcessing(file_directory=filename, default_settings=self.default_settings, global_settings=self.global_settings, config_path=self.config_path)
            self.photos.append(photo)
            photo_names.append(f'{str(i + 1)}. {str(photo)}')
        
        self.update_progress(80, 'Configuring GUI...')
        self.photoCombo.configure(values=photo_names) # configures dropdown to include list of photos
        self.photoCombo.current(0) # select the first photo to display

        self.update_progress(90, 'Loading photo...')
        self.load_IMG() # configure GUI to display the first photo
        self.update_progress(99)
        self.import_button.configure(state=tk.NORMAL)
        self.filemenu.entryconfigure('Import...', state=tk.NORMAL)
        self.update_UI()
        if self.glob_check.get() and self.global_settings != self.default_settings: # check if global settings are different from default on import
            self.unsaved = True # if it is the default, then it doesn't need to be saved
        else:
            self.unsaved = False
        self.hide_progress()
    
    def load_IMG(self, event=None):
        # Loading new image into GUI, loads other images in background
        def load_async(photo, i):
            # Threading function to load photo in background
            # photo: RawProcessing object
            # i: the index of the photo in self.photos
            photo.load()
            self.in_progress.remove(i)

        if len(self.photos) == 0:
            return
        photo_index = self.photoCombo.current()
        self.current_photo = self.photos[photo_index]
        self.glob_check.set(self.current_photo.use_global_settings)
        if self.current_photo.use_global_settings:
            self.apply_settings(self.current_photo, self.global_settings)
        self.change_settings() # Ensures that the GUI matches the photo's parameters
        if not self.current_photo.processed:
            self.current_photo.process() # only process photos if needed
        self.update_IMG()

        # conservatively load extra images in background to speed up switching, while saving memory
        for i, photo in enumerate(self.photos):
            if (abs(i - photo_index) <= self.advanced_settings['preload']) and not hasattr(photo, 'RAW_IMG') and i not in self.in_progress: # preload photos in buffer ahead or behind of the currently selected one
                threading.Thread(target=load_async, args=(photo, i), daemon=True).start()
                self.in_progress.add(i) # keeps track of photos in progress
            elif (abs(i - photo_index) > self.advanced_settings['preload']) and hasattr(photo, 'RAW_IMG'): # delete photos outside of buffer
                photo.clear_memory()

        self.set_disable_buttons()
    
    def update_IMG(self, full_res=True):
        # Loads new image into GUI
        # Queues full res picture to be loaded when ignore_full_res is set to False and the Full Preview is selected (default behaviour)
        def update_full_res():
            # Checks periodically if the thread is finished, then updates the image
            def check_if_done(t):
                if not t.is_alive():
                    if not self.current_photo.active_processes:
                        self.update_IMG(False) # update image, but do not queue full res process again
                else:
                    self.master.after(300, check_if_done, t) # if not done, wait some time, then check again
            t = threading.Thread(target=self.current_photo.process, args=[True, True, True], daemon=True) # Thread to generate full res previews
            t.start()
            self.master.after_idle(check_if_done, t)
        if len(self.photos) == 0:
            return
        try:
            if self.current_photo.get_IMG() is None:
                raise Exception
        except Exception as e:
            logger.exception(f'Exception: {e}')
            print(e)
            self.outputFrame.grid_forget()
            self.read_error_lbl.grid(row=0, column=1, sticky='EW') # displays error message when image cannot be loaded
            return
        
        self.read_error_lbl.grid_forget()
        self.outputFrame.grid(row=0, column=1, sticky='NSEW')
        if self.photo_process_Combo.current() == 4: # if "Full Preview" is selected
            self.process_photo_frame.grid_forget() # hide the process photo
            self.photo_display_height = max(int(self.master.winfo_height() - 100), 100) # resize image to full display height
        else:
            self.photo_display_height = max(int((self.master.winfo_height() - 100) / 2), 100)
            process_photo = ImageTk.PhotoImage(self.resize_IMG(self.current_photo.get_IMG(self.photo_process_values[self.photo_process_Combo.current()])))
            self.process_photo.configure(image=[process_photo])
            self.process_photo.image = process_photo
            self.process_photo_frame.grid(row=1, column=0)

        result_photo = ImageTk.PhotoImage(self.resize_IMG(self.current_photo.get_IMG()))
        self.result_photo.configure(image=[result_photo])
        self.result_photo.image = result_photo
        self.master.update()

        if full_res:
            # Generates full resolution image in the background
            if self.photo_process_Combo.current() == 4: # Only display when full preview is selected
                try: 
                    self.master.after_cancel(self.start_full_res)
                except: 
                    pass
                finally: 
                    self.start_full_res = self.master.after(500, update_full_res) # waits for 0.5 s of inactivity before processing

    def resize_IMG(self, img):  
        # Resizes the displayed image based on maximum allowable dimensions, while maintaining aspect ratio
        w, h = img.size
        scale = min(self.photo_display_width / w, self.photo_display_height / h)
        new_img = img.resize((int(w * scale), int(h * scale)))
        return new_img
    
    def resize_event(self, event=None):
        # Attempts to resize the images if the resize event has not been called for 100 ms
        try:
            self.master.after_cancel(self.resize)
        except: 
            pass
        finally:
            self.resize = self.master.after(100, self.resize_UI)
    
    def resize_UI(self):
        # Calculates the maximum dimensions for the displayed images based on the size of the window
        self.photo_display_width = max(int(self.master.winfo_width() - self.controlsFrame.winfo_width() - 20), 100)
        if self.photo_process_Combo.current() == 4:
            self.photo_display_height = max(int(self.master.winfo_height() - 100), 100)
        else:
            self.photo_display_height = max(int((self.master.winfo_height() - 100) / 2), 100)
        self.update_IMG(False)
    
    def previous(self):
        # Previous button
        if len(self.photos) == 0:
            return
        i = self.photoCombo.current()
        if i > 0:
            self.photoCombo.current(i - 1)
            self.load_IMG()
        self.set_disable_buttons()
    
    def next(self):
        # Next button
        if len(self.photos) == 0:
            return
        i = self.photoCombo.current()
        if i < len(self.photos) - 1:
            self.photoCombo.current(i + 1)
            self.load_IMG()
        self.set_disable_buttons()
    
    def set_disable_buttons(self):
        # Configures enable/disable states of next/previous buttons
        i = self.photoCombo.current()
        if i <= 0:
            self.prevButton.configure(state=tk.DISABLED)
        else:
            self.prevButton.configure(state=tk.NORMAL)
        if i + 1 >= len(self.photos):
            self.nextButton.configure(state=tk.DISABLED)
        else:
            self.nextButton.configure(state=tk.NORMAL)

    def set_global(self, event=None):
        # Defines behaviour of the 'Sync with Global Settings' checkbox
        if len(self.photos) == 0:
            return
        self.current_photo.use_global_settings = self.glob_check.get()
        self.apply_settings(self.current_photo, self.global_settings)
        self.change_settings()
        self.unsaved = True
        if self.glob_check.get():
            self.current_photo.process()
            self.update_IMG()

    def change_settings(self):
        # Configures GUI to reflect current applied settings for the photo
        for widget in self.widgets.values():
            widget.set(getattr(self.current_photo, widget.key))

        if self.current_photo.FileReadError:
            self.reject_check.disable()
        else:
            self.reject_check.enable()

        self.base_rgb.set(str(self.current_photo.base_rgb)) 
        self.rgb_display.configure(bg=self._from_rgb(self.current_photo.base_rgb))

        self.update_UI()

    def apply_settings(self, photo, settings):
        # applies settings to photo based on input dictionary containing settings
        for attribute in settings.keys():
            setattr(photo, attribute, settings[attribute])
    
    def changed_global_settings(self):
        # sets flags of all photos using global settings to be unprocessed when global settings are changed
        if len(self.photos) == 0:
            return
        for photo in self.photos:
            if photo.use_global_settings:
                photo.processed = False

    def reset_settings(self):
        # Reset settings to default parameters
        if len(self.photos) == 0:
            for widget in self.widgets.values():
                if widget.key in self.default_settings:
                    widget.set(self.default_settings[widget.key])
            return
        if self.glob_check.get():
            affected = sum([photo.use_global_settings for photo in self.photos]) # calculate the total number of photos using global settings
            if affected > 1:
                if not messagebox.askyesno('Reset to Default Settings',f'You are about to globally reset {str(affected)} photos\'s settings.\nDo you wish to continue?', icon='warning'):
                    return
            self.global_settings = self.default_settings.copy() # reset global settings
            self.changed_global_settings()
        self.apply_settings(self.current_photo, self.default_settings) # apply new settings to photo
        self.change_settings() # update GUI with new settings
        self.current_photo.process()
        self.update_IMG()
        self.unsaved = True
    
    # The following functions all define the behaviour of the interactable GUI, such as buttons, entries, and scales
    
    def update_UI(self):
        # Changes which settings are visible
        if (self.film_type.get() == 3) or self.reject_check.get():
            self.exposureFrame.grid_forget() # Hide the exposure frame when set to output RAW
        else:
            self.exposureFrame.grid(row=7, column=0, sticky='EW')

        if ((self.film_type.get()  == 1) or (self.film_type.get()  == 2)) and not self.reject_check.get():
            self.colourFrame.grid(row=6, column=0, sticky='EW') # Show the colour frame only for colour and slides
        else:
            self.colourFrame.grid_forget()
        
        if self.reject_check.get():
            self.cropFrame.grid_forget()
            self.globFrame.grid_forget()
            self.filmFrame.grid_forget()
            self.dustFrame.grid_forget()
            self.editmenu.entryconfigure('Reset to Default Settings', state=tk.DISABLED)
        else:
            self.cropFrame.grid(row=4, column=0, sticky='EW')
            self.globFrame.grid(row=1, column=0, sticky='EW')
            self.filmFrame.grid(row=3, column=0, sticky='EW')
            self.dustFrame.grid(row=4, column=0, sticky='EW')
            self.editmenu.entryconfigure('Reset to Default Settings', state=tk.NORMAL)
        
        if self.reject_check.get() or len(self.photos) == 0:
            self.current_photo_button.configure(state=tk.DISABLED)
        else:
            self.current_photo_button.configure(state=tk.NORMAL)
        
        if len([photo for photo in self.photos if not photo.reject]) == 0:
            self.all_photo_button.configure(state=tk.DISABLED)
        else:
            self.all_photo_button.configure(state=tk.NORMAL)
        
        if self.base_mode.get():
            self.base_clr_lbl.grid(row=1, column=0, sticky=tk.E)
            self.base_rgb_lbl.grid(row=1, column=1, sticky=tk.W)
            self.rgb_display.grid(row=1, column=2, sticky=tk.W)
            self.base_pick_button.grid(row=1, column=3, sticky=tk.W)
            self.base_buttons_frame.grid(row=2, column=0, columnspan=4, sticky='e')
        else:
            self.base_clr_lbl.grid_forget()
            self.base_rgb_lbl.grid_forget()
            self.rgb_display.grid_forget()
            self.base_pick_button.grid_forget()
            self.base_buttons_frame.grid_forget()
    
    def set_flip(self, event=None):
        if self.glob_check.get():
            affected = sum([photo.use_global_settings for photo in self.photos])
            if affected > 1:
                if messagebox.askyesno('Flip Photo', f'Do you want to globally flip {str(affected)} photos?', default='no'):
                    self.global_settings['flip'] = self.flip_check.get()
                    self.changed_global_settings()
                else:
                    self.glob_check.set(False)
                    self.current_photo.use_global_settings = False
            else:
                self.global_settings['flip'] = self.widgets['flip'].get()
                self.changed_global_settings()
        if len(self.photos) == 0:
            return
        self.current_photo.flip = self.widgets['flip'].get()
        self.update_IMG()
        self.unsaved = True
    
    def rot_clockwise(self, event=None):
        if len(self.photos) == 0:
            return
        if self.flip_check.get():
            self.current_photo.rotation -= 1
        else:
            self.current_photo.rotation += 1
        self.update_IMG()
        self.unsaved = True
    
    def rot_counterclockwise(self, event=None):
        if len(self.photos) == 0:
            return
        if self.flip_check.get():
            self.current_photo.rotation += 1
        else:
            self.current_photo.rotation -= 1
        self.update_IMG()
        self.unsaved = True

    def pick_wb(self):
        # Enables the white balance picker and cursor
        if len(self.photos) == 0:
            return
        self.wb_picker_button.state(['pressed']) # keeps the button pressed
        self.result_photo.configure(cursor='tcross') # changes the cursor over the preview to a cross
        self.result_photo_frame.configure(background='red') # highlights the preview image
        self.wb_picker = True # flag to indicate that the wb picker is enabled
        self.frame.set(0, True)

    def click(self, event):
        # Event handler for all clicks on GUI
        event.widget.focus_set() # if clicked anywhere, set focus to that widget
        if self.wb_picker and (event.widget != self.wb_picker_button):
            # Logic for if the white balance picker is selected
            self.wb_picker_button.state(['!pressed']) # reset button
            self.result_photo.configure(cursor='arrow') # reset cursor
            self.result_photo_frame.configure(background=self.master.cget('bg')) # reset frame
            self.wb_picker = False
            if event.widget == self.result_photo:
                x = event.x / event.widget.winfo_width()
                y = event.y / event.widget.winfo_height()
                self.current_photo.set_wb_from_picker(x, y) # set the white balance to neutral at the x, y coordinates of the mouse click

                self.temp.set(self.current_photo.temp)
                self.tint.set(self.current_photo.tint)

                if self.glob_check.get():
                    affected = sum([photo.use_global_settings for photo in self.photos])
                    if affected > 1:
                        if messagebox.askyesno('White Balance Picker', f'Do you want to apply this white balance adjustment globally to {str(affected)} photos?', default='no'):
                            self.global_settings['temp'] = self.temp.get()
                            self.global_settings['tint'] = self.tint.get()
                            self.changed_global_settings()
                        else:
                            self.glob_check.set(False)
                            self.current_photo.use_global_settings = False
                    else:
                        self.global_settings['temp'] = self.temp.get()
                        self.global_settings['tint'] = self.tint.get()
                        self.changed_global_settings()
                self.update_IMG()
                self.unsaved = True
        elif self.base_picker and (event.widget != self.base_pick_button):
            # Logic for if the base picker is selected
            self.base_pick_button.state(['!pressed']) # reset button
            self.process_photo.configure(cursor='arrow') # reset cursor
            self.process_photo_frame.configure(background=self.master.cget('bg')) # reset frane
            self.base_picker = False
            if event.widget == self.process_photo:
                x = event.x / event.widget.winfo_width()
                y = event.y / event.widget.winfo_height()
                self.current_photo.get_base_colour(x,y) # retrieve base colour at the x, y coordinates of the mouse click
                self.set_base_rgb(1)

    def set_base_detect(self, event=None):
        # Switches between auto base colour detect and manual setting
        if self.glob_check.get():
            affected = sum([photo.use_global_settings for photo in self.photos])
            if affected > 1:
                if messagebox.askyesno('Base Colour Changed', f'Do you want change the base colour globally to {str(affected)} photos?', default='no'):
                    self.global_settings['base_detect'] = self.base_mode.get()
                    self.changed_global_settings()
                else:
                    self.glob_check.set(False)
                    self.current_photo.use_global_settings = False
            else:
                self.global_settings['base_detect'] = self.base_mode.get()
                self.changed_global_settings()
        self.update_UI()
        if len(self.photos) == 0:
            return
        self.current_photo.base_detect = self.base_mode.get()
        self.current_photo.process(skip_crop=True)
        self.update_IMG()
        self.unsaved = True

    # logic to get the base rgb value, and configure the GUI accordingly
    def set_base_rgb(self, mode):
        match mode:
            case 0: # set rgb from colour picker
                try:
                    colour = self.current_photo.base_rgb
                except Exception as e: 
                    logger.exception(f'Exception: {e}')
                    colour = None
                rgb, _ = colorchooser.askcolor(colour, title='Enter Film Base RGB')
                if rgb is None:
                    return
            case 1: # pick colour from RAW image
                rgb = self.current_photo.base_rgb
            case 2: # pick colour from blank scan
                filename = filedialog.askopenfile(title='Select Blank Film Scan', filetypes=self.allowable_image_filetypes)
                try:
                    filename = filename.name
                except Exception as e: 
                    logger.exception(f'Exception: {e}')
                    return
                blank = RawProcessing(filename, self.default_settings, self.global_settings)
                blank.load()
                if blank.FileReadError:
                    messagebox.showerror('Read Blank', 'RAW image could not be read. Verify the integrity of the RAW image.')
                raw_img = cv2.convertScaleAbs(blank.RAW_IMG, alpha=(255.0/65535.0))[:,:,::-1]
                brightness = np.sum(raw_img.astype(np.uint16), 2)
                sample = np.percentile(brightness, 90) # take sample at 90th percentile brightest pixel
                index = np.where(brightness==sample)
                rgb = raw_img[index[0][0]][index[1][0]]
                rgb = tuple(rgb.tolist())

        if self.glob_check.get():
            self.global_settings['base_rgb'] = rgb
            self.changed_global_settings()
        self.base_rgb.set(str(rgb)) 
        self.rgb_display.configure(bg=self._from_rgb(rgb))
        if len(self.photos) == 0:
            return
        self.current_photo.base_rgb = rgb
        self.current_photo.process(skip_crop=True)
        self.update_IMG()
        self.unsaved = True
    
    def set_base(self):
        # enables the base colour picker
        if len(self.photos) == 0:
            return
        self.base_pick_button.state(['pressed']) # keeps the button pressed
        self.process_photo.configure(cursor='tcross') # changes the cursor over the preview to a cross
        self.photo_process_Combo.current(0) # display the RAW photo
        self.process_photo_frame.configure(background='red') # highlights the raw photo
        self.base_picker = True # flag to indicate that the wb picker is enabled
        self.update_IMG()
    
    def select_folder(self):
        # Dialog to select output destination folder
        destination_folder = filedialog.askdirectory() + '/' # opens dialog to choose folder
        if len(destination_folder) <= 1: # no input is given
            return
        self.destination_folder = destination_folder
        self.destination_folder_text.set(self.destination_folder) # display destination folder in GUI

    def export(self, n_photos=1):
        # Start export in seperate thread to keep UI responsive
        if len([photo for photo in self.photos if not photo.reject]) == 0:
            return
        if not self.destination_folder:
            self.destination_folder = "export"  # sets default export folder
        if not os.path.exists(self.destination_folder):
            os.makedirs(self.destination_folder)
            logger.info(f'Creating {self.destination_folder} folder')
        
        if n_photos == 1:
            export_fn = self.export_individual
        else:
            export_fn = self.export_multiple
        
        self.export_thread = threading.Thread(target=export_fn, daemon=True)
        self.export_thread.start()
    
    def export_individual(self):
        # Exports only photo that is currently visible
        if len(self.photos) == 0:
            return
        
        self.show_progress() # display progress bar

        self.current_photo_button.configure(state=tk.DISABLED)
        self.all_photo_button.configure(state=tk.DISABLED)
        self.import_button.configure(state=tk.DISABLED)
        self.filemenu.entryconfigure('Import...', state=tk.DISABLED)
        
        self.update_progress(20, 'Processing...') # Arbitrary progress display
        self.current_photo.load(True)
        self.current_photo.process(True)
        self.update_progress(99, 'Exporting photo...')
        filename = os.path.join(self.destination_folder, str(self.current_photo).split('.')[0]) # removes the file extension
        self.current_photo.export(filename) # saves the photo
        self.current_photo_button.configure(state=tk.NORMAL)
        self.all_photo_button.configure(state=tk.NORMAL)
        self.import_button.configure(state=tk.NORMAL)
        self.filemenu.entryconfigure('Import...', state=tk.NORMAL)
        self.hide_progress() # hide the progress bar
    
    def export_multiple(self):
        # This function exports all photos that are loaded. Uses multiprocessing to parallelize export.
        if len(self.photos) == 0:
            return
        self.show_progress('Applying photo settings...') # display progress bar
        self.current_photo_button.configure(state=tk.DISABLED)
        self.all_photo_button.pack_forget()
        self.abort_button.pack(side=tk.LEFT, padx=2, pady=5)
        self.import_button.configure(state=tk.DISABLED)
        self.filemenu.entryconfigure('Import...', state=tk.DISABLED)

        inputs = []
        allocated = 0 # sum of total allocated memory
        has_alloc = 0 # number of photos in which the memory allocation has been calculated
        with multiprocessing.Manager() as manager:
            self.terminate = manager.Event() # flag to abort export and safely close processes

            for photo in self.photos:
                if photo.reject:
                    continue
                if photo.use_global_settings:
                    self.apply_settings(photo, self.global_settings) # Ensures the proper settings have been applied
                filename = os.path.join(self.destination_folder, str(photo).split('.')[0]) # removes the file extension
                inputs.append((photo, filename, self.terminate, RawProcessing.class_parameters))
                if hasattr(photo, 'memory_alloc'):
                    allocated += photo.memory_alloc # tally of estimated memory requirements of each photo
                    has_alloc += 1
            
            if self.advanced_settings['max_processors_override'] != 0:
                max_processors = self.advanced_settings['max_processors_override']
            else:
                # limting the maximum number of processes based on available system memory
                available = psutil.virtual_memory()[1]
                #print('Available system RAM for export:', round(available / 1e9,1),'GB')
                allocated = allocated / has_alloc # allocated memory as average of estimated memory requirements for each photo
                #print(round(allocated / 1e9,1),'GB allocated')
                max_processors = round(available / allocated)
            processes = max(min(max_processors, multiprocessing.cpu_count(), len(inputs)), 1) # allocates number of processors between 1 and the maximum number of processors available
            #print(processes, 'processes allocated for export')

            self.update_progress(20, 'Allocating ' + str(processes) + ' processor(s) for export...')
            with multiprocessing.Pool(processes) as self.pool:
                i = 1
                errors = []
                for result in self.pool.imap(self.export_async, inputs):
                    if self.terminate.is_set():
                        self.pool.terminate()
                        break
                    if result:
                        errors.append(result) # keeps track of any errors raised
                        logger.exception(f'Exception: {result}') 
                    update_message = f'Exported {i} of {str(len(inputs))} photos.'
                    self.update_progress(i / len(inputs) * 80 + 19.99, update_message) # update progress display
                    i += 1
        if errors and not self.terminate.is_set():
            # if errors are raised, display dialog with errors
            errors_display = 'Details:'
            for i, error in enumerate(errors, 1):
                errors_display += f'\n {str(i)}. {str(error)}'
            messagebox.showerror(f'Export Error: {len(errors)}) export(s) failed.\n' + errors_display)

        self.current_photo_button.configure(state=tk.NORMAL)
        self.abort_button.pack_forget()
        self.all_photo_button.pack(side=tk.LEFT, padx=2, pady=5)
        self.import_button.configure(state=tk.NORMAL)
        self.filemenu.entryconfigure('Import...', state=tk.NORMAL)
        self.hide_progress() # hide the progress bar

    def abort(self):
        # Stop the export
        try:
            self.terminate.set()
        except Exception:
            pass
    
    # Defines how to show and hide the progress bar
    def show_progress(self, message=''):
        self.progressFrame.grid(row=10, column=0, sticky='NEW')
        self.update_progress(0, message)
    
    def hide_progress(self):
        self.progressFrame.grid_forget()
    
    def update_progress(self, percentage, message=''):
        # takes number between 0 and 100 to display progress, with optional parameter to display message
        self.progress.set(percentage)
        self.progress_percentage.configure(text=f'{str(round(percentage))}%')
        self.progress_msg.configure(text=message)
        self.master.update()

    def key_handler(self, event):
        # Maps various keybinds to different functions
        if not hasattr(self, 'previous_view'):
            self.previous_view = 0  # Default to RAW

        match event.keysym:
            case 'Right':
                self.next()
            case 'Left':
                self.previous()
            case 'r':
                self.rot_clockwise()
            case 'R':
                self.rot_counterclockwise()
            case 'q':
                self.previous_view = 0
                self.photo_process_Combo.current(0) # RAW
                self.update_IMG()
            case 'w':
                self.previous_view = 1
                self.photo_process_Combo.current(1) # Threshold
                self.update_IMG()
            case 'e':
                self.previous_view = 2
                self.photo_process_Combo.current(2) # Contours
                self.update_IMG()
            case 'h':
                self.previous_view = 3
                self.photo_process_Combo.current(3) # Histogram
                self.update_IMG()
            case 'f':
                current_view = self.photo_process_Combo.current()
                if current_view == 4:
                    self.photo_process_Combo.current(self.previous_view) # Return to previous
                else:
                    self.photo_process_Combo.current(4) # Full Preview
                self.update_IMG()

    def set_tooltip(self, widget, text, delay=500):
        # Adds a tooltip to a provided widget showing the provided text when the mouse is hovering over the widget
        tooltip = tk.Label(self.master, text=f"{text}", bg="white", relief="solid", borderwidth=1, anchor="w", justify="left", padx=3, pady=1)
        tooltip_timer = None
        def show_tooltip():
            tooltip.place(x=widget.winfo_rootx() - self.master.winfo_rootx() + 10, 
                        y=widget.winfo_rooty() - self.master.winfo_rooty() + 30)
        def schedule_tooltip(event):
            nonlocal tooltip_timer
            tooltip_timer = self.master.after(delay, show_tooltip)
        def cancel_tooltip(event):
            nonlocal tooltip_timer
            if tooltip_timer:
                self.master.after_cancel(tooltip_timer)
                tooltip_timer = None
            tooltip.place_forget()
        widget.bind("<Enter>", schedule_tooltip)
        widget.bind("<Leave>", cancel_tooltip)
        
    def on_closing(self):
        # Behaviour/cleanup at closing
        if len(self.photos) > 0:
            if self.ask_save_settings() is None: # if "Cancel" is pressed, do nothing
                return
        if hasattr(self, 'export_thread') and self.export_thread.is_alive(): # check if the export thread is still alive
            if messagebox.askyesno(title='Export in Progress', icon='warning', message='Export is still in progress. Do you really want to quit?', default='no'):
                try:
                    self.pool.terminate()
                except Exception as e:
                    logger.exception(f'Exception: {e}') 
            else:
                return
        self.master.destroy() # quit program

    def ask_save_settings(self):
        # dialog to ask if settings are to be saved. If yes, saves settings and returns True. No returns False. Cancel returns None.
        if self.unsaved:
            result = messagebox.askyesnocancel('Unsaved Changes', 'Do you want to save the changes you made to this batch of photos?')
        else:
            return False
        if result:
            self.save_settings()
        return result
    
    def save_settings(self, event=None):
        # loops through all the photos and applies global settings where needed, then saves the settings to disk
        for photo in self.photos:
            if photo.use_global_settings:
                self.apply_settings(photo, self.global_settings) # apply most current settings before saving
            photo.save_settings()
        self.unsaved = False

    def copy_settings(self, event=None):
        # copies the current photo's settings
        if len(self.photos) == 0:
            return
        self.copied_settings = {}
        for key in self.default_settings:
            self.copied_settings[key] = getattr(self.current_photo, key)
        self.editmenu.entryconfig('Paste Settings', state=tk.NORMAL)
        
    def paste_settings(self, event=None):
        # pastes the copied settings if self.copy_settings() has been called
        # if pasted into a photo with global settings applied, asks if the user wants to apply to all photos with global settings
        if hasattr(self, 'copied_settings') and hasattr(self, 'current_photo'):
            self.apply_settings(self.current_photo, self.copied_settings)
            if self.current_photo.use_global_settings:
                affected = sum([photo.use_global_settings for photo in self.photos])
                if affected > 1:
                    if messagebox.askyesno('Paste Settings', f'Do you want to paste the settings globally to {str(affected)} photos?'):
                        self.global_settings = self.copied_settings
                        self.changed_global_settings()
                    else:
                        self.glob_check.set(False)
                        self.current_photo.use_global_settings = False
                else:
                    self.global_settings = self.copied_settings
            self.change_settings()
            self.current_photo.process()
            self.update_IMG()
            self.unsaved = True
    
    @staticmethod
    def _from_rgb(rgb):
        # translates an rgb tuple of int to a tkinter friendly color code
        return '#%02x%02x%02x' % rgb
    
    @staticmethod
    def export_async(inputs):
        # used by multiprocessing
        photo, filename, terminate, class_parameters = inputs
        # photo: RawProcessing object
        # filename: the directory and filename to be saved as
        # terminate: multiprocessing.Event flag to tell the process to stop
        # class_parameters: class variables
        RawProcessing.class_parameters = class_parameters
        for _ in range(5):
            try:
                if terminate.is_set():
                    return
                photo.load(True)
                if photo.FileReadError:
                    raise Exception('File could not be read')
                if terminate.is_set():
                    return
                photo.process(True) # process photo in full quality
            except Exception as e:
                error = e
            else:
                if terminate.is_set():
                    return
                photo.export(filename)
                photo.clear_memory()
                return False
        return error
