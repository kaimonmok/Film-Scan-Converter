import os
import psutil
import sys
from tkinter import ttk,  filedialog, messagebox, colorchooser
import tkinter as tk
from PIL import ImageTk
import rawpy
import threading
import numpy as np 
import cv2
import multiprocessing

#custom classes
from ScrollFrame import ScrollFrame
from RawProcessing import RawProcessing

#logging
import logging

logger = logging.getLogger(__name__)
FORMAT = '%(asctime)s:::%(levelname)s:::%(message)s'
logging.basicConfig(filename='logfile.log', level=logging.DEBUG, format=FORMAT)

class GUI:
    def __init__(self, master):
        # Initialize Variables
        self.photos = []
        self.in_progress = set() # keeps track photos that are in processing when first loading
        self.photo_process_values = ['RAW', 'Threshold', 'Contours', 'Histogram', 'Full Preview']
        self.filetypes = ['TIFF', 'PNG', 'JPG'] # Export File Types
        self.destination_folder = ''
        self.allowable_image_filetypes = [
            ('RAW files', '*.DNG *.CR2 *.CR3 *.NEF *.ARW *.RAF *.ERF *.GPR *.RAW *.CRW *.dng *.cr2 *.cr3 *.nef *.arw *.raf *.erf *.grp *.raw *.crw'),
            ('Image files', '*.PNG *.JPG *.JPEG *.BMP *.TIFF *.TIF *.png *.jpg *.jpeg *.bmp *.tiff *.tif')
            ]
        self.header_style = ('Segoe UI', 10, 'normal') # Defines font for section headers
        self.wb_picker = False
        self.base_picker = False
        self.unsaved = False # Indicates that settings have changed need to be saved

        self.max_processors_override = 0 # 0 means disabled
        self.preload = 4 # Buffer size to preload photos
        self.advanced_attrs = ('max_processors_override','preload') # attributes that will be picked up for modification in advanced settings

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
            logger.exception(f"Exception: {e}")
        self.master.geometry('800x500')
        validation = self.master.register(self.validate)

        menubar = tk.Menu(self.master, relief=tk.FLAT)
        self.filemenu = tk.Menu(menubar, tearoff=0)
        self.filemenu.add_command(label='Import...', command=self.import_photos)
        self.filemenu.add_command(label='Save Settings', command=self.save_settings)
        self.filemenu.add_separator()
        self.filemenu.add_command(label='Exit', command=self.on_closing)
        menubar.add_cascade(label='File', menu=self.filemenu)
        self.editmenu = tk.Menu(menubar, tearoff=0)
        self.editmenu.add_command(label='Reset to Default Settings', command=self.reset_settings)
        self.editmenu.add_separator()
        self.editmenu.add_command(label='Advanced Settings...', command=self.advanced_dialog)
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
        self.nextButton = ttk.Button(importSubFrame2, text='Next Photo >', width=20, command=self.next)
        self.nextButton.pack(side=tk.LEFT, padx=2, pady=5)

        # Processing Frame
        processing_title = ttk.Label(text='Processing Settings', font=self.header_style, padding=2)
        processingFrame = ttk.LabelFrame(dynamic_scroll_frame.frame, borderwidth=2, labelwidget=processing_title, padding=5)
        processingFrame.grid(row=1, column=0, sticky='EW')
        # Reject Checkbutton to exclude from export
        rejectFrame = ttk.Frame(processingFrame)
        rejectFrame.grid(row=0, column=0, sticky='EW')
        ttk.Label(rejectFrame, text='Reject Photo:').pack(side=tk.LEFT)
        self.reject_check = tk.BooleanVar()
        self.reject_check.set(False)
        self.reject_CheckButton = ttk.Checkbutton(rejectFrame, variable=self.reject_check, state='deselected', command=self.set_reject)
        self.reject_CheckButton.pack(side=tk.LEFT)
        # Selection of global settings
        self.globFrame = ttk.Frame(processingFrame)
        self.globFrame.grid(row=1, column=0, sticky='EW')
        ttk.Label(self.globFrame, text='Sync with Global Settings:').pack(side=tk.LEFT)
        self.glob_check = tk.BooleanVar()
        self.glob_check.set(True)
        ttk.Checkbutton(self.globFrame, variable=self.glob_check, state='selected', command=self.set_global).pack(side=tk.LEFT)
        # Selection of film type
        self.filmFrame = ttk.Frame(processingFrame)
        self.filmFrame.grid(row=3, column=0, sticky='EW')
        ttk.Label(self.filmFrame, text='Film Type:').pack(side=tk.LEFT)
        self.filmCombo = ttk.Combobox(self.filmFrame, state='readonly', values=['Black & White Negative', 'Colour Negative', 'Slide (Colour Positive)','Crop Only (RAW)'], width=25)
        self.filmCombo.current(self.global_settings['film_type'])
        self.filmCombo.pack(side=tk.LEFT, padx=2)
        self.filmCombo.bind('<<ComboboxSelected>>', self.set_film_type)
        # Dust removal
        self.dustFrame = ttk.Frame(processingFrame)
        self.dustFrame.grid(row=4, column=0, sticky='EW')
        ttk.Label(self.dustFrame, text='Remove Dust:').pack(side=tk.LEFT)
        self.dust_check = tk.BooleanVar()
        self.dust_check.set(self.global_settings['remove_dust'])
        ttk.Checkbutton(self.dustFrame, variable=self.dust_check, state='deselected', command=self.set_remove_dust).pack(side=tk.LEFT)

        # Automatic Cropping Settings
        controls_title = ttk.Label(text='Automatic Crop & Rotate', font=self.header_style, padding=2)
        self.cropFrame = ttk.LabelFrame(dynamic_scroll_frame.frame, borderwidth=2, labelwidget=controls_title, padding=5)
        self.cropFrame.grid(row=4, column=0, sticky='EW')
        crop_adjustments = ttk.Frame(self.cropFrame)
        crop_adjustments.pack(fill='x')
        crop_adjustments.grid_rowconfigure(1, weight=1)
        crop_adjustments.grid_columnconfigure(3, weight=1)
        ttk.Label(crop_adjustments, text='Dark Threshold:').grid(row=0, column=0, sticky=tk.E)
        self.dark_threshold = tk.IntVar()
        self.dark_threshold.set(self.global_settings['dark_threshold'])
        self.dark_threshold_scale = ttk.Scale(crop_adjustments, from_=0, to=100, orient=tk.HORIZONTAL, command=lambda x:self.dark_threshold.set(round(float(x))), length=100, value=self.dark_threshold.get())
        self.dark_threshold_scale.grid(row=0, column=1, padx=2)
        self.dark_threshold_scale.bind('<ButtonRelease-1>', self.set_dark_threshold)
        self.dark_threshold_spin = ttk.Spinbox(crop_adjustments, from_=0, to=100, increment=1, textvariable=self.dark_threshold, command=self.set_dark_threshold, width=5, validate='key', validatecommand=(validation, '%P', '%W'))
        self.dark_threshold_spin.grid(row=0, column=2)
        self.dark_threshold_spin.bind('<Return>', self.set_dark_threshold)
        self.dark_threshold_spin.bind('<FocusOut>', self.set_dark_threshold)
        ttk.Label(crop_adjustments, text='Light Threshold:').grid(row=1, column=0, sticky=tk.E)
        self.light_threshold = tk.IntVar()
        self.light_threshold.set(self.global_settings['light_threshold'])
        self.light_threshold_scale = ttk.Scale(crop_adjustments, from_=0, to=100, orient=tk.HORIZONTAL, command=lambda x:self.light_threshold.set(round(float(x))), length=100, value=self.light_threshold.get())
        self.light_threshold_scale.grid(row=1, column=1, padx=2)
        self.light_threshold_scale.bind('<ButtonRelease-1>', self.set_light_threshold)
        self.light_threshold_spin = ttk.Spinbox(crop_adjustments, from_=0, to=100, increment=1, textvariable=self.light_threshold, command=self.set_light_threshold, width=5, validate='key', validatecommand=(validation, '%P', '%W'))
        self.light_threshold_spin.grid(row=1, column=2)
        self.light_threshold_spin.bind('<Return>', self.set_light_threshold)
        self.light_threshold_spin.bind('<FocusOut>', self.set_light_threshold)
        ttk.Label(crop_adjustments, text='Border Crop (%):').grid(row=2, column=0, sticky=tk.E)
        self.border_crop = tk.IntVar()
        self.border_crop.set(self.global_settings['border_crop'])
        self.bc_scale = ttk.Scale(crop_adjustments, from_=0, to=20, orient=tk.HORIZONTAL, command=lambda x:self.border_crop.set(round(float(x))), length=100, value=self.border_crop.get())
        self.bc_scale.grid(row=2, column=1, padx=2)
        self.bc_scale.bind('<ButtonRelease-1>', self.set_border_crop)
        self.bc_spin = ttk.Spinbox(crop_adjustments, from_=0, to=20, textvariable=self.border_crop, width=5, command=self.set_border_crop, validate='key', validatecommand=(validation, '%P', '%W'))
        self.bc_spin.grid(row=2, column=2)
        self.bc_spin.bind('<Return>', self.set_border_crop)
        self.bc_spin.bind('<FocusOut>', self.set_border_crop)
        ttk.Label(crop_adjustments, text='Flip Horizontally:').grid(column=0, row=3, sticky=tk.E)
        self.flip_check = tk.BooleanVar()
        self.flip_check.set(self.global_settings['flip'])
        ttk.Checkbutton(crop_adjustments, variable=self.flip_check, state='selected', command=self.set_flip).grid(column=1, row=3, sticky=tk.W)
        rotButtons = ttk.Frame(self.cropFrame)
        rotButtons.pack(fill='x')
        ttk.Button(rotButtons, text='Rotate Counterclockwise', width=22, command=self.rot_counterclockwise).pack(side=tk.LEFT, padx=2, pady=5)
        ttk.Button(rotButtons, text='Rotate Clockwise', width=22, command=self.rot_clockwise).pack(side=tk.LEFT, padx=2, pady=5)

        # Colour settings
        if getattr(sys, 'frozen', False):
            picker = tk.PhotoImage(file=os.path.join(sys._MEIPASS, 'dropper.png')).subsample(15,15)
        else:
            picker = tk.PhotoImage(file='dropper.png').subsample(15,15)
        colour_title = ttk.Label(text='Colour Adjustment', font=self.header_style, padding=2)
        self.colourFrame = ttk.LabelFrame(dynamic_scroll_frame.frame, borderwidth=2, labelwidget=colour_title, padding=5)
        colour_controls = ttk.Frame(self.colourFrame)
        colour_controls.pack(fill='x', side=tk.LEFT)
        ttk.Label(colour_controls, text='Film Base Colour:').grid(row=0, column=0, sticky=tk.E)
        self.base = ttk.Combobox(colour_controls, values=['Auto Detect','Set Manually'], state='readonly', width=12)
        self.base.grid(row=0, column=1, columnspan=2, sticky=tk.W, padx=2)
        self.base.current(self.global_settings['base_detect'])
        self.base.bind('<<ComboboxSelected>>', self.set_base_detect)
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
        ttk.Label(colour_controls, text='Temperature:').grid(row=4, column=0, sticky=tk.E, padx=2, pady=2)
        self.temp = tk.IntVar()
        self.temp.set(self.global_settings['temp'])
        self.temp_scale = ttk.Scale(colour_controls, from_=-100, to=100, orient=tk.HORIZONTAL, command=lambda x:self.temp.set(round(float(x)/5)*5), length=100, value=self.temp.get())
        self.temp_scale.grid(row=4, column=1, padx=2)
        self.temp_scale.set(self.global_settings['temp'])
        self.temp_scale.bind('<ButtonRelease-1>', self.set_temp)
        self.temp_spin = ttk.Spinbox(colour_controls, from_=-100, to=100, increment=5, textvariable=self.temp, width=5, command=self.set_temp, validate='key', validatecommand=(validation, '%P', '%W'))
        self.temp_spin.grid(row=4, column=2, sticky=tk.W, columnspan=2)
        self.temp_spin.bind('<Return>', self.set_temp)
        self.temp_spin.bind('<FocusOut>', self.set_temp)
        ttk.Label(colour_controls, text='Tint:').grid(row=5, column=0, sticky=tk.E)
        self.tint = tk.IntVar()
        self.tint.set(self.global_settings['tint'])
        self.tint_scale = ttk.Scale(colour_controls, from_=-100, to=100, orient=tk.HORIZONTAL, command=lambda x:self.tint.set(round(float(x)/5)*5), length=100, value=self.tint.get())
        self.tint_scale.grid(row=5, column=1, padx=2)
        self.tint_scale.set(self.global_settings['tint'])
        self.tint_scale.bind('<ButtonRelease-1>', self.set_tint)
        self.tint_spin = ttk.Spinbox(colour_controls, from_=-100, to=100, increment=5, textvariable=self.tint, width=5, command=self.set_tint, validate='key', validatecommand=(validation, '%P', '%W'))
        self.tint_spin.grid(row=5, column=2, sticky=tk.W, columnspan=2)
        self.tint_spin.bind('<Return>', self.set_tint)
        self.tint_spin.bind('<FocusOut>', self.set_tint)
        ttk.Label(colour_controls, text='Saturation (%):').grid(row=6, column=0, sticky=tk.E)
        self.sat = tk.IntVar()
        self.sat.set(self.global_settings['sat'])
        self.sat_scale = ttk.Scale(colour_controls, from_=0, to=200, orient=tk.HORIZONTAL, command=lambda x:self.sat.set(round(float(x)/10)*10), length=100, value=self.sat.get())
        self.sat_scale.grid(row=6, column=1, padx=2)
        self.sat_scale.set(self.global_settings['sat'])
        self.sat_scale.bind('<ButtonRelease-1>', self.set_sat)
        self.sat_spin = ttk.Spinbox(colour_controls, from_=0, to=200, increment=10, textvariable=self.sat, width=5, command=self.set_sat, validate='key', validatecommand=(validation, '%P', '%W'))
        self.sat_spin.grid(row=6, column=2, sticky=tk.W, columnspan=2)
        self.sat_spin.bind('<Return>', self.set_sat)
        self.sat_spin.bind('<FocusOut>', self.set_sat)
        
        # Brightness Settings
        brightness_title = ttk.Label(text='Brightness Adjustment', font=self.header_style, padding=2)
        self.exposureFrame = ttk.LabelFrame(dynamic_scroll_frame.frame, borderwidth=2, labelwidget=brightness_title, padding=5)
        self.exposureFrame.grid(row=7, column=0, sticky='EW')
        exposureControls = ttk.Frame(self.exposureFrame)
        exposureControls.pack(fill='x', side=tk.LEFT)
        exposureControls.grid_rowconfigure(6, weight=1)
        exposureControls.grid_columnconfigure(3, weight=1)
        ttk.Label(exposureControls, text='White Point:').grid(row=2, column=0, sticky=tk.E)
        self.white_point = tk.IntVar()
        self.white_point.set(self.global_settings['white_point'])
        self.wpp_scale = ttk.Scale(exposureControls, from_=-100, to=100, orient=tk.HORIZONTAL, command=lambda x:self.white_point.set(round(float(x)/5)*5), length=100, value=self.white_point.get())
        self.wpp_scale.grid(row=2, column=1, padx=2)
        self.wpp_scale.set(self.global_settings['white_point'])
        self.wpp_scale.bind('<ButtonRelease-1>', self.set_white_point)
        self.wpp_spin = ttk.Spinbox(exposureControls, from_=-100, to=100, increment=5, textvariable=self.white_point, width=5, command=self.set_white_point, validate='key', validatecommand=(validation, '%P', '%W'))
        self.wpp_spin.grid(row=2, column=2, sticky=tk.W)
        self.wpp_spin.bind('<Return>', self.set_white_point)
        self.wpp_spin.bind('<FocusOut>', self.set_white_point)
        ttk.Label(exposureControls, text='Black Point:').grid(row=3, column=0, sticky=tk.E)
        self.black_point = tk.IntVar()
        self.black_point.set(self.global_settings['black_point'])
        self.bpp_scale = ttk.Scale(exposureControls, from_=-100, to=100, orient=tk.HORIZONTAL, command=lambda x:self.black_point.set(round(float(x)/5)*5), length=100, value=self.black_point.get())
        self.bpp_scale.grid(row=3, column=1, padx=2)
        self.bpp_scale.set(self.global_settings['black_point'])
        self.bpp_scale.bind('<ButtonRelease-1>', self.set_black_point)
        self.bpp_spin = ttk.Spinbox(exposureControls, from_=-100, to=100, increment=5, textvariable=self.black_point, width=5, command=self.set_black_point, validate='key', validatecommand=(validation, '%P', '%W'))
        self.bpp_spin.grid(row=3, column=2, sticky=tk.W)
        self.bpp_spin.bind('<Return>', self.set_black_point)
        self.bpp_spin.bind('<FocusOut>', self.set_black_point)
        ttk.Label(exposureControls, text='Gamma:').grid(row=4, column=0, sticky=tk.E)
        self.gamma = tk.IntVar()
        self.gamma.set(self.global_settings['gamma'])
        self.gamma_scale = ttk.Scale(exposureControls, from_=-100, to=100, orient=tk.HORIZONTAL, command=lambda x:self.gamma.set(round(float(x)/5)*5), length=100, value=self.gamma.get())
        self.gamma_scale.grid(row=4, column=1, padx=2)
        self.gamma_scale.set(self.global_settings['gamma'])
        self.gamma_scale.bind('<ButtonRelease-1>', self.set_gamma)
        self.gamma_spin = ttk.Spinbox(exposureControls, from_=-100, to=100, increment=5, textvariable=self.gamma, width=5, command=self.set_gamma, validate='key', validatecommand=(validation, '%P', '%W'))
        self.gamma_spin.grid(row=4, column=2, sticky=tk.W)
        self.gamma_spin.bind('<Return>', self.set_gamma)
        self.gamma_spin.bind('<FocusOut>', self.set_gamma)
        ttk.Label(exposureControls, text='Shadows:').grid(row=5, column=0, sticky=tk.E)
        self.shadows = tk.IntVar()
        self.shadows.set(self.global_settings['shadows'])
        self.shad_scale = ttk.Scale(exposureControls, from_=-100, to=100, orient=tk.HORIZONTAL, command=lambda x:self.shadows.set(round(float(x)/5)*5), length=100, value=self.shadows.get())
        self.shad_scale.grid(row=5, column=1, padx=2)
        self.shad_scale.set(self.global_settings['shadows'])
        self.shad_scale.bind('<ButtonRelease-1>', self.set_shadows)
        self.shad_spin = ttk.Spinbox(exposureControls, from_=-100, to=100, increment=5, textvariable=self.shadows, width=5, command=self.set_shadows, validate='key', validatecommand=(validation, '%P', '%W'))
        self.shad_spin.grid(row=5, column=2, sticky=tk.W)
        self.shad_spin.bind('<Return>', self.set_shadows)
        self.shad_spin.bind('<FocusOut>', self.set_shadows)
        ttk.Label(exposureControls, text='Highlights:').grid(row=6, column=0, sticky=tk.E)
        self.highlights = tk.IntVar()
        self.highlights.set(self.global_settings['highlights'])
        self.high_scale = ttk.Scale(exposureControls, from_=-100, to=100, orient=tk.HORIZONTAL, command=lambda x:self.highlights.set(round(float(x)/5)*5), length=100, value=self.highlights.get())
        self.high_scale.grid(row=6, column=1, padx=2)
        self.high_scale.set(self.global_settings['highlights'])
        self.high_scale.bind('<ButtonRelease-1>', self.set_highlights)
        self.high_spin = ttk.Spinbox(exposureControls, from_=-100, to=100, increment=5, textvariable=self.highlights, width=5, command=self.set_highlights, validate='key', validatecommand=(validation, '%P', '%W'))
        self.high_spin.grid(row=6, column=2, sticky=tk.W)
        self.high_spin.bind('<Return>', self.set_highlights)
        self.high_spin.bind('<FocusOut>', self.set_highlights)

        # Export photo settings
        export_title = ttk.Label(text='Export Settings', font=self.header_style, padding=2)
        export_frame = ttk.LabelFrame(dynamic_scroll_frame.frame, borderwidth=2, labelwidget=export_title, padding=5)
        export_frame.grid(row=9, column=0, sticky='EW')
        export_settings_frame = ttk.Frame(export_frame)
        export_settings_frame.pack(fill='x')
        ttk.Label(export_settings_frame, text='Export File Type:', anchor='w').grid(row=0, column=0, sticky=tk.E)
        self.filetype_Combo = ttk.Combobox(export_settings_frame, state='readonly', values=self.filetypes, width=15)
        self.filetype_Combo.current(2)
        self.filetype_Combo.grid(row=0, column=1, sticky=tk.W, padx=2, columnspan=2)
        ttk.Label(export_settings_frame, text='White Frame (%):', anchor='w').grid(row=1, column=0, sticky=tk.E)
        self.frame = tk.IntVar()
        self.frame.set(RawProcessing.frame)
        self.frame_scale = ttk.Scale(export_settings_frame, from_=0, to=10, orient=tk.HORIZONTAL, command=lambda x:self.frame.set(round(float(x))), length=100, value=self.frame.get())
        self.frame_scale.grid(row=1, column=1, sticky=tk.W, pady=5, padx=2)
        self.frame_scale.set(self.frame.get())
        self.frame_scale.bind('<ButtonRelease-1>', self.set_frame)
        frame_spin = ttk.Spinbox(export_settings_frame, from_=0, to=10, increment=1, textvariable=self.frame, validate='key', validatecommand=(validation, '%P', '%W'), command=self.set_frame, width=5)
        frame_spin.grid(row=1, column=2, sticky=tk.W, pady=5)
        frame_spin.bind('<Return>', self.set_frame)
        frame_spin.bind('<FocusOut>', self.set_frame)
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
        self.progressFrame = ttk.Frame(dynamic_scroll_frame.frame, padding=2)
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
        self.read_error_lbl = ttk.Label(mainFrame, text='Error: File could not be read', font=('Segoe UI', 20), justify="center", anchor='center')
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

        self.master.bind('<Configure>', self.resize_event)
        self.master.bind('<Key>', self.key_handler)
        self.master.bind('<Button>', self.click)
        self.master.protocol('WM_DELETE_WINDOW', self.on_closing)
        dynamic_scroll_frame.update()

        self.set_disable_buttons()
        try:
            params_dict = np.load('config.npy', allow_pickle=True).item()
        except Exception as e:
            logger.exception(f"Exception: {e}")
        else:
            for object in [self, RawProcessing]:
                for attr in object.advanced_attrs:
                    if attr in params_dict:
                        setattr(object, attr, params_dict[attr]) # Initializes every parameter with imported parameters

    def advanced_dialog(self):
        # Pop-up window to contain all the advanced settings that don't fit in the main controls
        class EntryLabel:
            # Defines custom widget with label with a spinbox next to it
            def __init__(widget, master, text, min, max, default_values, tkVar, increment=1, format='', width=10):
                nonlocal row
                def focus_in(variable):
                    widget.prev_value = variable.get() # when selected, store the current value for later

                def fix_num(variable):
                    # Keeps the input numeric and in-bounds
                    try:
                        variable.get()
                    except tk.TclError:
                        variable.set(widget.prev_value)
                    else:
                        if not is_float:
                            variable.set(round(variable.get()))
                        if variable.get() < min:
                            variable.set(min)
                        elif variable.get() > max:
                            variable.set(max)
                        widget.prev_value = variable.get()
                    top.focus()

                def numeric(input):
                    # validates the input as numeric and in bounds
                    try:
                        x = float(input)
                    except ValueError:
                        return False
                    else:
                        if not input.isnumeric() and not is_float:
                            return False
                        elif x < min:
                            return False
                        elif x > max:
                            return False
                        else:
                            return True
                
                validation = top.register(numeric)
                widget.variables_list = []
                is_float = tkVar == tk.DoubleVar
                try:
                    iter(default_values)
                except TypeError:
                    default_values = [default_values]
                
                widget.label = ttk.Label(master, text=text)
                widget.label.grid(row=row, column=0, sticky=tk.E)
                widget.entryFrame = ttk.Frame(master, width=20)
                widget.entryFrame.grid(row=row, column=1, sticky='new', padx=5, pady=2)
                widget.entryFrame.columnconfigure(0, weight=1)
                for i, value in enumerate(default_values):
                    variable = tkVar()
                    variable.set(value)
                    widget.variables_list.append(variable)
                    invalid = top.register(lambda: fix_num(variable))
                    spinbox = ttk.Spinbox(widget.entryFrame, textvariable=variable, from_=min, to=max, increment=increment, validate='focusout', validatecommand=(validation, '%P'), invalidcommand=invalid, format=format, width=width)
                    spinbox.grid(row=0, column=i, sticky='new')
                    spinbox.bind('<Return>', lambda x: fix_num(variable))
                    spinbox.bind('<FocusIn>', lambda x:focus_in(variable))
                row += 1
            def get(widget):
                # Returns the value of the entry
                output = tuple([var.get() for var in widget.variables_list])
                if len(output) == 1:
                    return output[0]
                else:
                    return output
            
            def show(widget):
                widget.label.grid(row=row, column=0, sticky=tk.E)
                widget.entryFrame.grid(row=row, column=1, sticky='new', padx=5, pady=2)
            
            def hide(widget):
                widget.label.grid_forget()
                widget.entryFrame.grid_forget()
        
        class ComboLabel:
            # Defines custom widget with a label and a dropdown menu next to it
            def __init__(widget, master, text, values, variable):
                nonlocal row
                ttk.Label(master, text=text).grid(row=row, column=0, sticky=tk.E)
                ttk.Combobox(master, textvariable=variable, values=values, state='readonly').grid(row=row, column=1, sticky='new', padx=5, pady=2)
                row += 1
        
        class CheckLabel:
            # Defines custom widget with a label and checkbox
            def __init__(widget, master, text, value, command):
                widget.variable = tk.BooleanVar()
                widget.variable.set(value)
                ttk.Label(master, text=text).grid(row=row, column=0, sticky=tk.E)
                ttk.Checkbutton(master, variable=widget.variable, command=command).grid(row=row, column=1, sticky='new', padx=5, pady=2)

            def get(widget):
                return widget.variable.get()
        
        def set_wb():
            # Hides or shows wb multipliers if using wb from camera
            if use_camera_wb.get():
                wb_mult.hide()
            else:
                wb_mult.show()

        def apply_settings():
            RawProcessing.max_proxy_size = max_proxy_size.get()
            RawProcessing.jpg_quality = jpg_quality.get()
            RawProcessing.dm_alg = allowable_dm_algs[dm_algs_list.index(dm_alg.get())]
            RawProcessing.colour_space = cs_list.index(colour_space.get())
            RawProcessing.tiff_compression = t_comp_dict[tiff_compression.get()]
            RawProcessing.exp_shift = exp_shift.get()
            RawProcessing.fbdd_nr = fbdd_nr_list.index(fbdd_nr.get())
            RawProcessing.raw_gamma = raw_gamma.get()
            RawProcessing.use_camera_wb = use_camera_wb.get()
            RawProcessing.wb_mult = list(wb_mult.get())
            RawProcessing.white_point_percentile = white_point_percentile.get()
            RawProcessing.black_point_percentile = black_point_percentile.get()
            RawProcessing.ignore_border = ignore_border.get()
            RawProcessing.dust_threshold = dust_threshold.get()
            RawProcessing.dust_iter = dust_iter.get()
            RawProcessing.max_dust_area = max_dust_area.get()
            self.max_processors_override = max_processors.get()
            self.preload = preload.get()
            
            quit()
            for photo in self.photos:
                photo.clear_memory()
            self.load_IMG()
        
        def save_settings():
            # saves the advanced settings as a config.npy file
            apply_settings()
            params_dict = dict()
            for attr in RawProcessing.advanced_attrs:
                params_dict[attr] = getattr(RawProcessing, attr)
            for attr in self.advanced_attrs:
                params_dict[attr] = getattr(self, attr)
            np.save('config.npy', params_dict)
        
        def quit():
            self.master.attributes('-topmost', 0)
            top.destroy()

        top = tk.Toplevel(self.master)
        top.transient(self.master)
        top.title('Advanced Settings')
        top.grab_set()
        top.bind('<Button>', lambda event: event.widget.focus_set())
        top.resizable(False, False)
        top.focus_set()
        top.transient(self.master)
        top.protocol('WM_DELETE_WINDOW', quit)
        self.master.attributes('-topmost', 1)

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

        row = 0 # starting row

        # Building pop-up GUI
        dm_alg = tk.StringVar()
        allowable_dm_algs = (0, 1, 2, 3, 4, 11, 12)
        dm_algs_list = ('LINEAR','VNG','PPG','AHD','DCB','DHT','AAHD')
        dm_alg.set(dm_algs_list[allowable_dm_algs.index(RawProcessing.dm_alg)])
        ComboLabel(import_settings, 'Demosaicing Algorithm:', dm_algs_list, dm_alg)

        colour_space = tk.StringVar()
        cs_list = ('raw','sRGB','Adobe','Wide','ProPhoto','XYZ','ACES','P3D65','Rec2020')
        colour_space.set(cs_list[RawProcessing.colour_space])
        ComboLabel(import_settings, 'RAW Output Colour Space:', cs_list, colour_space)

        raw_gamma = EntryLabel(import_settings, 'RAW Gamma (Power, Slope):', 0, 8, RawProcessing.raw_gamma, tk.DoubleVar, 0.1, width=10)

        exp_shift = EntryLabel(import_settings, 'RAW Exposure Shift:', -2, 3, RawProcessing.exp_shift, tk.IntVar)

        fbdd_nr = tk.StringVar()
        fbdd_nr_list = ('Off','Light','Full')
        fbdd_nr.set(fbdd_nr_list[RawProcessing.fbdd_nr])
        ComboLabel(import_settings, 'FBDD Noise Reduction:', fbdd_nr_list, fbdd_nr)

        use_camera_wb = CheckLabel(import_settings, 'Use Camera White Balance:', RawProcessing.use_camera_wb, set_wb)

        try:
            wb_lbl = 'White Balance Multipliers (' + self.current_photo.colour_desc + '):'
        except Exception as e:
            logger.exception(f"Exception: {e}")
            wb_lbl = 'White Balance Multipliers:'
        wb_mult = EntryLabel(import_settings, wb_lbl, 0, 4, RawProcessing.wb_mult, tk.DoubleVar, 0.1, width=4)
        set_wb()

        max_proxy_size = EntryLabel(process_settings, 'Max Proxy Size (W + H):', 500, 20000, RawProcessing.max_proxy_size, tk.IntVar, 500)

        preload = EntryLabel(process_settings, 'Photo Preload Buffer Size:', 0, 20, self.preload, tk.IntVar)

        ignore_border = EntryLabel(process_settings, 'EQ Ignore Borders % (W, H):', 0, 40, RawProcessing.ignore_border, tk.IntVar)

        white_point_percentile = EntryLabel(process_settings, 'White Point Percentile:', 70, 100, RawProcessing.white_point_percentile, tk.DoubleVar)

        black_point_percentile = EntryLabel(process_settings, 'Black Point Percentile:', 0, 30, RawProcessing.black_point_percentile, tk.DoubleVar)

        dust_threshold = EntryLabel(dust_settings, 'Threshold:', 0, 50, RawProcessing.dust_threshold, tk.IntVar)

        dust_iter = EntryLabel(dust_settings, 'Noise Closing Iterations:', 1, 10, RawProcessing.dust_iter, tk.IntVar)

        max_dust_area = EntryLabel(dust_settings, 'Max Particle Area:', 0, 100, RawProcessing.max_dust_area, tk.IntVar)

        jpg_quality = EntryLabel(export_settings, 'JPEG Quality:', 0, 100, RawProcessing.jpg_quality, tk.IntVar, 10)

        tiff_compression = tk.StringVar()
        t_comp_dict = {
            'No Compression': 1,
            'Lempel-Ziv & Welch': 5,
            'Adobe Deflate (ZIP)': 8,
            'PackBits': 32773
            }
        tiff_compression.set(list(t_comp_dict.keys())[list(t_comp_dict.values()).index(RawProcessing.tiff_compression)])
        ComboLabel(export_settings, 'TIFF Compression:', list(t_comp_dict), tiff_compression)

        max_processors = EntryLabel(export_settings, 'Max Processors Override:', 0, multiprocessing.cpu_count(), self.max_processors_override, tk.IntVar)

        buttonFrame = ttk.Frame(mainFrame)
        buttonFrame.grid(row=1, column=0, columnspan=2, sticky='e')
        ttk.Button(buttonFrame, text='Cancel', command=quit).pack(side=tk.RIGHT, padx=2, pady=5, anchor='sw')
        ttk.Button(buttonFrame, text='Save', command=save_settings).pack(side=tk.RIGHT, padx=2, pady=5, anchor='sw')

        # Centres pop-up window over self.master window
        top.update_idletasks()
        x = self.master.winfo_x() + int((self.master.winfo_width()/2) - (top.winfo_width()/2))
        y = self.master.winfo_y() + int((self.master.winfo_height()/2) - (top.winfo_height()/2))
        top.geometry('+%d+%d' % (x, y))

    def validate(self, input, widget):
        # Validates if the input is numeric
        def set_value(value):
            # Function to replace value in current widget
            self.master.nametowidget(widget).delete(0,'end')
            self.master.nametowidget(widget).insert(0, value)
        if input == '' or input == '-':
            set_value(0)
        elif input == '0-':
            set_value('-0') # allows negative numbers to be more easily entered
        try: 
            int(input)
        except ValueError:
            return False # input is non-numeric
        else:
            # Get rid of leading zeros
            if input[0] == '0':
                set_value(input[1:])
            elif (input[:2] == '-0') and (len(input) > 2):
                set_value('-' + input[2:])
            return True
    
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
            photo = RawProcessing(file_directory=filename, default_settings=self.default_settings, global_settings=self.global_settings)
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
            if (abs(i - photo_index) <= self.preload) and not hasattr(photo, 'RAW_IMG') and i not in self.in_progress: # preload photos in buffer ahead or behind of the currently selected one
                threading.Thread(target=load_async, args=(photo, i), daemon=True).start()
                self.in_progress.add(i) # keeps track of photos in progress
            elif (abs(i - photo_index) > self.preload) and hasattr(photo, 'RAW_IMG'): # delete photos outside of buffer
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
            logger.exception(f"Exception: {e}")
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
                except Exception as _: 
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
        except Exception as e: 
                     logger.exception(f"Exception: {e}")
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

    def set_reject(self, event=None):
        # Defines behaviour of the 'Discard' checkbox
        if len(self.photos) > 0:
            self.current_photo.reject = self.reject_check.get()
        self.update_UI()
        self.unsaved = True

    def set_global(self, event=None):
        # Defines behaviour of the 'Use Global Settings' checkbox
        if len(self.photos) == 0:
            return
        self.current_photo.use_global_settings = self.glob_check.get()
        self.apply_settings(self.current_photo, self.global_settings)
        self.change_settings()
        self.unsaved = True
        if self.glob_check.get():
            self.current_photo.process()
            self.update_IMG()

    def change_settings(self, reset=False):
        # Configures GUI to reflect current applied settings for the photo
        self.reject_check.set(self.current_photo.reject)

        if self.current_photo.FileReadError:
            self.reject_CheckButton.configure(state=tk.DISABLED)
        else:
            self.reject_CheckButton.configure(state=tk.NORMAL)
        
        self.filmCombo.current(self.current_photo.film_type)

        self.dust_check.set(self.current_photo.remove_dust)

        self.dark_threshold.set(self.current_photo.dark_threshold)
        self.dark_threshold_scale.set(self.current_photo.dark_threshold)

        self.light_threshold.set(self.current_photo.light_threshold)
        self.light_threshold_scale.set(self.current_photo.light_threshold)

        self.border_crop.set(self.current_photo.border_crop)
        self.bc_scale.set(self.current_photo.border_crop)

        self.flip_check.set(self.current_photo.flip)

        self.white_point.set(self.current_photo.white_point)
        self.wpp_scale.set(self.current_photo.white_point)

        self.black_point.set(self.current_photo.black_point)
        self.bpp_scale.set(self.current_photo.black_point)

        self.gamma.set(self.current_photo.gamma)
        self.gamma_scale.set(self.current_photo.gamma)

        self.shadows.set(self.current_photo.shadows)
        self.shad_scale.set(self.current_photo.shadows)

        self.highlights.set(self.current_photo.highlights)
        self.high_scale.set(self.current_photo.highlights)

        self.temp.set(self.current_photo.temp)
        self.temp_scale.set(self.current_photo.temp)

        self.tint.set(self.current_photo.tint)
        self.tint_scale.set(self.current_photo.tint)
        
        self.sat.set(self.current_photo.sat)
        self.sat_scale.set(self.current_photo.sat)

        self.base.current(self.current_photo.base_detect)
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

    def set_film_type(self, event=None):
        if self.glob_check.get():
            self.global_settings['film_type'] = self.filmCombo.current()
            self.changed_global_settings()
        self.update_UI()
        if len(self.photos) == 0:
            return
        self.current_photo.film_type = self.filmCombo.current()
        self.current_photo.process()
        self.update_IMG()
        self.unsaved = True
    
    def update_UI(self):
        # Changes which settings are visible
        if (self.filmCombo.current() == 3) or self.reject_check.get():
            self.exposureFrame.grid_forget() # Hide the exposure frame when set to output RAW
        else:
            self.exposureFrame.grid(row=7, column=0, sticky='EW')

        if ((self.filmCombo.current() == 1) or (self.filmCombo.current() == 2)) and not self.reject_check.get():
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
        
        if self.base.current():
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
    
    def set_remove_dust(self, event=None):
        if self.glob_check.get():
            self.global_settings['remove_dust'] = self.dust_check.get()
            self.changed_global_settings()
        if len(self.photos) == 0:
            return
        self.current_photo.remove_dust = self.dust_check.get()
        self.update_IMG()
        self.unsaved = True
            
    def set_dark_threshold(self, event=None):
        if self.glob_check.get():
            self.global_settings['dark_threshold'] = self.dark_threshold.get()
            self.changed_global_settings()
        self.dark_threshold_scale.set(self.dark_threshold.get())
        if len(self.photos) == 0:
            return
        self.current_photo.dark_threshold = self.dark_threshold.get()
        self.current_photo.process()
        self.update_IMG()
        self.unsaved = True

    def set_light_threshold(self, event=None):
        if self.glob_check.get():
            self.global_settings['light_threshold'] = self.light_threshold.get()
            self.changed_global_settings()
        self.light_threshold_scale.set(self.light_threshold.get())
        if len(self.photos) == 0:
            return
        self.current_photo.light_threshold = self.light_threshold.get()
        self.current_photo.process()
        self.update_IMG()
        self.unsaved = True
    
    def set_border_crop(self, event=None):
        if self.glob_check.get():
            self.global_settings['border_crop'] = self.border_crop.get()
            self.changed_global_settings()
        self.bc_scale.set(self.border_crop.get())
        if len(self.photos) == 0:
            return
        self.current_photo.border_crop = self.border_crop.get()
        self.current_photo.process()
        self.update_IMG()
        self.unsaved = True
    
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
                self.global_settings['flip'] = self.flip_check.get()
                self.changed_global_settings()
        if len(self.photos) == 0:
            return
        self.current_photo.flip = self.flip_check.get()
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
    
    def set_white_point(self, event=None):
        if self.glob_check.get():
            self.global_settings['white_point'] = self.white_point.get()
            self.changed_global_settings()
        self.wpp_scale.set(self.white_point.get())
        if len(self.photos) == 0:
            return
        self.current_photo.white_point = self.white_point.get()
        self.current_photo.process(skip_crop=True)
        self.update_IMG()
        self.unsaved = True
    
    def set_black_point(self, event=None):
        if self.glob_check.get():
            self.global_settings['black_point'] = self.black_point.get()
            self.changed_global_settings()
        self.bpp_scale.set(self.black_point.get())
        if len(self.photos) == 0:
            return
        self.current_photo.black_point = self.black_point.get()
        self.current_photo.process(skip_crop=True)
        self.update_IMG()
        self.unsaved = True

    def set_gamma(self, event=None):
        if self.glob_check.get():
            self.global_settings['gamma'] = self.gamma.get()
            self.changed_global_settings()
        self.gamma_scale.set(self.gamma.get())
        if len(self.photos) == 0:
            return
        self.current_photo.gamma = self.gamma.get()
        self.current_photo.process(skip_crop=True)
        self.update_IMG()
        self.unsaved = True
    
    def set_shadows(self, event=None):
        if self.glob_check.get():
            self.global_settings['shadows'] = self.shadows.get()
            self.changed_global_settings()
        self.shad_scale.set(self.shadows.get())
        if len(self.photos) == 0:
            return
        self.current_photo.shadows = self.shadows.get()
        self.current_photo.process(skip_crop=True)
        self.update_IMG()
        self.unsaved = True
    
    def set_highlights(self, event=None):
        if self.glob_check.get():
            self.global_settings['highlights'] = self.highlights.get()
            self.changed_global_settings()
        self.high_scale.set(self.highlights.get())
        if len(self.photos) == 0:
            return
        self.current_photo.highlights = self.highlights.get()
        self.current_photo.process(skip_crop=True)
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
                self.current_photo.set_wb_from_picker(x, y) # set the white balance to neutral at the x, y cooredinates of the mouse click

                self.temp.set(self.current_photo.temp)
                self.temp_scale.set(self.current_photo.temp)

                self.tint.set(self.current_photo.tint)
                self.tint_scale.set(self.current_photo.tint)

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
                    self.global_settings['base_detect'] = self.base.current()
                    self.changed_global_settings()
                else:
                    self.glob_check.set(False)
                    self.current_photo.use_global_settings = False
            else:
                self.global_settings['base_detect'] = self.base.current()
                self.changed_global_settings()
        self.update_UI()
        if len(self.photos) == 0:
            return
        self.current_photo.base_detect = self.base.current()
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
                    logger.exception(f"Exception: {e}")
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
                    logger.exception(f"Exception: {e}")
                    return
                try:
                    with rawpy.imread(filename) as raw: # tries to read as raw file
                        raw_img = raw.postprocess(
                            output_bps = 8, # output 8-bit image
                            use_camera_wb = RawProcessing.use_camera_wb, # Screws up the colours if not used
                            user_wb = RawProcessing.wb_mult, # wb multipliers
                            demosaic_algorithm = rawpy.DemosaicAlgorithm(RawProcessing.dm_alg),
                            output_color = rawpy.ColorSpace(RawProcessing.colour_space),
                            gamma = RawProcessing.raw_gamma, # Guessed random numbers, these seemed to work the best
                            auto_bright_thr = 0, # no clipping of highlights
                            exp_preserve_highlights = 1,
                            exp_shift = 2 ** RawProcessing.exp_shift,
                            half_size = True # take the average of 4 pixels to reduce resolution
                            )
                except Exception as _:
                    try:
                        raw_img = cv2.imread(filename) # if fails, reads as normal image
                        if type(raw_img) is not np.ndarray:
                            raise Exception(f'{filename} failed to load!')
                        raw_img = raw_img[:,:,::-1] # converts BGR to RGB
                    except Exception as e: # If fails again, generate error message
                        logger.error("The selected image could not be read.")
                        logger.exception(f"Exception: {e}") 
                        messagebox.showerror('Error: File Read Error','The selected image could not be read.')
                        return
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

    def set_temp(self, event=None):
        if self.glob_check.get():
            self.global_settings['temp'] = self.temp.get()
            self.changed_global_settings()
        self.temp_scale.set(self.temp.get())
        if len(self.photos) == 0:
            return
        self.current_photo.temp = self.temp.get()
        self.current_photo.process(skip_crop=True)
        self.update_IMG()
        self.unsaved = True
    
    def set_tint(self, event=None):
        if self.glob_check.get():
            self.global_settings['tint'] = self.tint.get()
            self.changed_global_settings()
        self.tint_scale.set(self.tint.get())
        if len(self.photos) == 0:
            return
        self.current_photo.tint = self.tint.get()
        self.current_photo.process(skip_crop=True)
        self.update_IMG()
        self.unsaved = True

    def set_sat(self, event=None):
        if self.glob_check.get():
            self.global_settings['sat'] = self.sat.get()
            self.changed_global_settings()
        self.sat_scale.set(self.sat.get())
        if len(self.photos) == 0:
            return
        self.current_photo.sat = self.sat.get()
        self.current_photo.process(skip_crop=True)
        self.update_IMG()
        self.unsaved = True

    def set_frame(self, event=None):
        # Adds a decorative white border to final output
        if self.frame.get() > 10:
            self.frame.set(10)
        elif self.frame.get() < 0:
            self.frame.set(0)
        self.frame_scale.set(self.frame.get())
        RawProcessing.frame = self.frame.get()
        self.update_IMG()
    
    def select_folder(self):
        # Dialog to select output destination folder
        self.destination_folder = filedialog.askdirectory() + '/' # opens dialog to choose folder
        if len(self.destination_folder) <= 1:
            return
        self.destination_folder_text.set(self.destination_folder) # display destination folder in GUI

    def export(self, n_photos=1):
        # Start export in seperate thread to keep UI responsive
        if len([photo for photo in self.photos if not photo.reject]) == 0:
            return
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
        filename = self.destination_folder + str(self.current_photo).split('.')[0] # removes the file extension
        filename = filename + '.' + self.filetypes[self.filetype_Combo.current()]  # sets the file extension
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

        filetype = self.filetypes[self.filetype_Combo.current()] # sets the file type for export

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
                filename = self.destination_folder + str(photo).split('.')[0] # removes the file extension
                filename = f'{filename}.{filetype}' # creates file path with file name and extension
                inputs.append((photo, filename, self.terminate))
                if hasattr(photo, 'memory_alloc'):
                    allocated += photo.memory_alloc # tally of estimated memory requirements of each photo
                    has_alloc += 1
            
            if self.max_processors_override != 0:
                max_processors = self.max_processors_override
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
                        logger.exception(f"Exception: {result}") 
                    update_message = f'Exported {i} of {str(len(inputs))} photos.'
                    self.update_progress(i / len(inputs) * 80 + 19.99, update_message) # update progress display
                    i += 1
        if errors and not self.terminate.is_set():
            # if errors are raised, display dialog with errors
            errors_display = 'Details:'
            for i, error in enumerate(errors, 1):
                errors_display += f'\n {str(i)}. {str(error)}'
            messagebox.showerror(f'Export Error {len(errors)}) export(s) failed.\n' + errors_display)

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
        except Exception as e:
            logger.exception(f"Exception: {e}") 
    
    # Defines how to show and hide the progress bar
    def show_progress(self, message=''):
        self.progressFrame.grid(row=10, column=0, sticky='EW')
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
        # Maps left and right arrow keys to show previous or next photo respectively
        match event.keysym:
            case 'Right':
                self.next()
            case 'Left':
                self.previous()
    
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
                    logger.exception(f"Exception: {e}") 
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
    
    def save_settings(self):
        # loops through all the photos and applies global settings where needed, then saves the settings to disk
        for photo in self.photos:
            if photo.use_global_settings:
                self.apply_settings(photo, self.global_settings) # apply most current settings before saving
            photo.save_settings()
        self.unsaved = False
    
    @staticmethod
    def _from_rgb(rgb):
        # translates an rgb tuple of int to a tkinter friendly color code
        return '#%02x%02x%02x' % rgb
    
    @staticmethod
    def export_async(inputs):
        # used by multiprocessing
        photo, filename, terminate = inputs
        # photo: RawProcessing object
        # filename: the directory and filename to be saved as
        # terminate: multiprocessing.Event flag to tell the process to stop
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