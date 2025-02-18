import rawpy
import cv2
import numpy as np
from PIL import Image
import matplotlib.colors
import os
import piexif

import logging

logger = logging.getLogger(__name__)
FORMAT = '%(asctime)s:::%(levelname)s:::%(message)s'
logging.basicConfig(filename='logfile.log', level=logging.DEBUG, format=FORMAT)

class RawProcessing:
    # This class defines a photo object that contains the image processing pipeline from raw to final export, including all processing functions and parameters
    default_parameters = dict(
        max_proxy_size = 2000, # Max dimension of height + width to increase processing speed (only for previews)
        histogram_plt_size = (1600, 2400, 3), # Dimensions of the histogram
        hist_bg_colour = (25, 25, 25), # sets the background colour of the histogram
        frame = 0, # adds white frame to final photo
        jpg_quality = 90, # from 0-100
        tiff_compression = 8, # defines the tiff compression algorithm
        dm_alg = 2, # demosaicing algorithm
        colour_space = 7, # output colour space after demosaicing
        exp_shift = 3.0, # number of stops to adjust the raw
        fbdd_nr = 0, # noise reduction on demosaic
        raw_gamma = (2.222, 4.5), # (power, slope) for RAW image
        use_camera_wb = True, # use built-in wb parameters from camera
        wb_mult = [1, 1, 1, 1], # multipliers for each 2x2 bayer pattern
        noise_thr = 0, # for RAW denoising
        median_filter_passes = 0, # can reduce colour artifacts during demosaicing
        black_point_percentile = 0.5, # sets the black point
        white_point_percentile = 99.0, # sets the default white balance as a percentile of the brightest pixels
        ignore_border = (1, 1), # ignores the border for calculation of histogram EQ
        ignore_neg_border = True, # ignores negative border space for calculation of histogram EQ
        dust_threshold = 10,
        max_dust_area = 15,
        dust_iter = 5,
        picker_radius = 0.5,
        filetype = 'JPG',
        fit_aspect_ratio = 'Keep Original'
    )
    class_parameters = default_parameters.copy()
    advanced_attrs = [key for key in default_parameters.keys() if key not in ('filetype', 'frame', 'fit_aspect_ratio')] # list of keys for advanced settings, except for keys that should not be saved
    processing_parameters = ('dark_threshold','light_threshold','border_crop','flip','rotation','film_type','white_point','black_point','gamma','shadows','highlights','temp','tint','sat','reject','base_detect','base_rgb','remove_dust')
    
    exif_parameters = dict(
        camera_make = '',
        camera_model = '',
        lens_make = '',
        lens_model = '',
        date_time_original = ''
    )

    def __init__(self, file_directory, default_settings, global_settings, config_path):
        # file_directory: the name of the RAW file to be processed
        # Instance Variables
        self.processed = False # flag for whether the image has been processed yet
        self.proxy = False # Flag to keep track of whether or not proxies are being used
        self.FileReadError = False # flag for if the class could not read the RAW file
        self.active_processes = 0 # lets object know how many processes are currently processing the photo
        self.pick_wb = False # flag to pick white balance from a set of pixel coordinates
        self.file_directory = file_directory
        self.filename = os.path.basename(self.file_directory)
        self.colour_desc = None # RAW bayer colour description
        self.config_path = config_path
        # initializing raw processing parameters
        try: # to read in the parameters from a saved file
            directory = os.path.join(self.config_path, f"{self.filename.split('.')[0]}.npy")
            params_dict = np.load(directory, allow_pickle=True).item()
        except Exception as e:# file does not exist
            logger.exception(f'Exception: {e}')
            for attr in self.processing_parameters:
                if attr in global_settings:
                    setattr(self, attr, global_settings[attr]) # Initializes every instance parameter based on default value
                else:
                    setattr(self, attr, 0) # otherwise set to 0
            self.use_global_settings = True # tells GUI class whether to overwrite current photo settings with global setting
        else: # import successful
            for attr in self.processing_parameters:
                if attr in params_dict:
                    setattr(self, attr, params_dict[attr]) # Initializes every instance parameter with imported parameters
                elif attr in default_settings:
                    setattr(self, attr, default_settings[attr]) # if parameter doesn't exist, use default
                else:
                    setattr(self, attr, 0) # otherwise set to 0

            self.use_global_settings = False # tells GUI class whether to overwrite current photo settings with global setting
    
    def load(self, full_res=False):
        # Loads the RAW file into memory
        try:
            with rawpy.imread(self.file_directory) as raw: # tries to read as raw file
                self.RAW_IMG = raw.postprocess(
                    output_bps = 16, # output 16-bit image
                    use_camera_wb = self.class_parameters['use_camera_wb'], # Screws up the colours if not used
                    user_wb = self.class_parameters['wb_mult'], # wb multipliers
                    demosaic_algorithm = rawpy.DemosaicAlgorithm(self.class_parameters['dm_alg']),
                    fbdd_noise_reduction = rawpy.FBDDNoiseReductionMode(self.class_parameters['fbdd_nr']),
                    output_color = rawpy.ColorSpace(self.class_parameters['colour_space']),
                    gamma = self.class_parameters['raw_gamma'],
                    auto_bright_thr = 0, # no clipping of highlights
                    median_filter_passes = self.class_parameters['median_filter_passes'],
                    noise_thr = self.class_parameters['noise_thr'],
                    exp_preserve_highlights = 1,
                    exp_shift = 2 ** self.class_parameters['exp_shift'],
                    half_size = not full_res # take the average of 4 pixels to reduce resolution and computational requirements
                    )
                self.colour_desc = raw.color_desc.decode('utf-8') # get the bayer pattern
        except Exception as _:
            try:
                self.RAW_IMG = cv2.imread(self.file_directory) # if fails, reads as normal image
                if type(self.RAW_IMG) is not np.ndarray:
                    raise Exception(f'{self.file_directory} failed to load!')
            except Exception as e:
                logger.exception(f'Exception: {e}') # If fails again, set error attributes
                self.reject = True
                self.FileReadError = True
                return
            else:
                if self.RAW_IMG.dtype == np.uint8:
                    self.RAW_IMG = (self.RAW_IMG).astype(np.uint16, copy=False) * 256 # converts image to 16-bit
        else:
            # RawPy sometimes misreads the RAW image size, this removes any extra black borders
            gray = cv2.cvtColor(cv2.convertScaleAbs(self.RAW_IMG, alpha=(255.0/65535.0)),cv2.COLOR_RGB2GRAY)
            _, thresh = cv2.threshold(gray,0,255,0)
            contours, _ = cv2.findContours(thresh,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            del gray, thresh
            cnt = max(contours, key=cv2.contourArea)
            x,y,w,h = cv2.boundingRect(cnt)
            self.RAW_IMG = self.RAW_IMG[y:y+h,x:x+w,::-1]
        
        self.FileReadError = False
        self.memory_alloc = self.RAW_IMG.nbytes * 4 * 12 # estimation of memory requirements based on the size of the image

    def get_IMG(self, output=None, as_array=False):
        # Returns the converted image at different stages of the process, based on desired output
        if self.FileReadError: # Return nothing when file could not be read
            return
        match output:
            case 'RAW': # return RAW image
                img = self.rotate(self.RAW_IMG) # apply rotation to image
            case 'Threshold': # return threshold image
                img = self.thresh
                img = self.rotate(img) # apply rotation to image
            case 'Contours': # generate contour image, then return it
                thresh_img = np.uint8(cv2.cvtColor(self.thresh, cv2.COLOR_GRAY2BGR) / 2)
                thresh_img[:,:,2] = 0 # sets colour of threshold image

                indices = np.indices(thresh_img.shape[:2])
                zebra_width = int(np.max(indices) / 100)
                zebra = np.repeat((np.mod(indices[0] + indices[1], zebra_width * 2) > zebra_width)[:, :, np.newaxis], 3, axis=2)
                thresh_img = np.where(zebra, 0, thresh_img) # applies zebra pattern to threshold image
                img = cv2.addWeighted(cv2.convertScaleAbs(self.RAW_IMG, alpha=(255.0/65535.0)), 1, thresh_img, 0.2, 0) # add threshold image to RAW

                # drawing crop boxes
                if self.rect is not None:
                    border_width = np.ceil((img.shape[0] + img.shape[1]) / 800) # border width proportional to image size
                    if img.shape[0] > img.shape[1]:
                        x_crop = self.border_crop
                        y_crop = self.border_crop * img.shape[1] / img.shape[0]
                    else:
                        y_crop = self.border_crop
                        x_crop = self.border_crop * img.shape[0] / img.shape[1]
                    y, x = img.shape[0], img.shape[1]
                    rect = ((self.rect[0][0]*y, self.rect[0][1]*x), (self.rect[1][0]*y, self.rect[1][1]*x), self.rect[2])
                    box = cv2.boxPoints(rect)
                    box = np.int64(box)
                    extra_crop_box = self.shrink_box(box, x_crop, y_crop)

                    EQ_ignore_box = extra_crop_box.copy()
                    ignore_border = np.array(self.class_parameters['ignore_border'])
                    if self.border_crop < 0 and self.class_parameters['ignore_neg_border']:
                        EQ_ignore_box = self.shrink_box(EQ_ignore_box, -x_crop, -y_crop)
                    EQ_ignore_box = self.shrink_box(EQ_ignore_box, ignore_border[0], ignore_border[1])
                    EQ_ignore_poly = np.zeros_like(img)
                    cv2.fillPoly(EQ_ignore_poly, [extra_crop_box], (0,0,255))
                    cv2.fillPoly(EQ_ignore_poly, [EQ_ignore_box], (0,0,0))
                    img = np.where(np.dstack([np.sum(EQ_ignore_poly, (2)) == 0]*3), img, cv2.addWeighted(EQ_ignore_poly, 2, img, 0.8, 0)) # shaded zone where EQ calcs are ignored
                    
                    cv2.drawContours(img,[box],0,(0,255,255), int(border_width * 0.75)) # original crop
                    cv2.drawContours(img, self.largest_contour, -1, (0,255,255), int(border_width * .75)) # largest contour
                    cv2.drawContours(img,[extra_crop_box],0,(0,255,0), int(border_width)) # extra border crop
                img = self.rotate(img) # apply rotation to image
            case 'Histogram': # returns histogram of preview image
                img = self.draw_histogram(self.IMG)
                img = np.flip(img, 0)
                mask = np.sum(img, 2) == 0
                img[mask] = np.array(self.class_parameters['hist_bg_colour'])
            case _: # default case, return preview image
                img = self.IMG
                if self.remove_dust:
                    img = self.fill_dust(img, self.dust_mask)
                img = self.add_frame(img) # add decorative white frame
                img = self.rotate(img) # apply rotation to image
        if as_array:
            return img
        else:
            if img.dtype == 'uint16':
                img = cv2.convertScaleAbs(img, alpha=(255.0/65535.0))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB) # Convert back to RGB
            return Image.fromarray(img) # convert image to tkinter-friendly image
        
    def __str__(self):
        # returns file name when str() is called on photo
        return os.path.basename(self.file_directory)
    
    def get_exif_bytes(self):
        # Builds a valid exif data structure based on the exif parameters and the given image as bytes
        # Returns bytes containing the exif data structure for images
        zeroth_ifd = {
            piexif.ImageIFD.Make: self.exif_parameters['camera_make'],
            piexif.ImageIFD.Model: self.exif_parameters['camera_model'],
            piexif.ImageIFD.Software: "Film Scan Converter"
        }
        exif_ifd = {
            piexif.ExifIFD.DateTimeOriginal: self.exif_parameters['date_time_original'],
            piexif.ExifIFD.LensMake: self.exif_parameters['lens_make'],
            piexif.ExifIFD.LensModel: self.exif_parameters['lens_model'],
        }
        gps_ifd = {
            # placeholder for further development
        }
        first_ifd = {
            # placeholder for further development
        }

        # piexif expects this dict structure
        exif_dict = {
            '0th':zeroth_ifd,
            'Exif':exif_ifd,
            'GPS':gps_ifd,
            '1st':first_ifd,
            'thumbnail': None
        }

        return piexif.dump(exif_dict)

    def export(self, filename):
        # Saves final image to disk.
        # filename is a string containing the directory and file name with the file extension
        if not hasattr(self, 'IMG'):
            return
        img = self.get_IMG(as_array=True)
        filename = f"{filename}.{self.class_parameters['filetype']}"
        match self.class_parameters['filetype']:
            case 'JPG':
                img_8bit = cv2.convertScaleAbs(img, alpha=(255.0/65535.0)) # Must convert to 8-bit image before exporting as JPG
                img_pil = Image.fromarray(cv2.cvtColor(img_8bit, cv2.COLOR_RGB2BGR))
                exif = self.get_exif_bytes()

                img_pil.save(filename, format='JPEG', quality=self.class_parameters['jpg_quality'], exif=exif)
            case 'TIFF':
                quality = [cv2.IMWRITE_TIFF_COMPRESSION, self.class_parameters['tiff_compression']]
                cv2.imwrite(filename, img, quality)
            case _:
                cv2.imwrite(filename, img)

    def save_settings(self):
        # saves the processing parameters to a file
        directory = os.path.join(self.config_path, f"{self.filename.split('.')[0]}.npy") # uses the same name as the input file
        params_dict = dict()
        for attr in self.processing_parameters:
            params_dict[attr] = getattr(self, attr)
        np.save(directory, params_dict)
    
    def process(self, full_res=False, recent_only=False, skip_crop=False):
        # Selection of appropriate film processing type
        # full_res uses the full resolution raw image for processing, otherwise use downsampled proxy
        # recent_only will not update final output if multiple, more recent processes are started before it finishes
        # skip_crop: skip calculating crop (faster if crop parameters have not changed)
        if not hasattr(self, 'RAW_IMG'):
            self.load() # tries to load file if it hasn't already been done
        if self.FileReadError:
            return # Do not process if the file could not be read
        self.active_processes += 1 # Used to keep track of the number of processes currently running

        if not skip_crop or not hasattr(self, 'thresh'):
            self.thresh, self.rect, self.largest_contour = self.find_optimal_crop()
            
            img_size = self.RAW_IMG.shape[0] + self.RAW_IMG.shape[1]
            if (img_size > self.class_parameters['max_proxy_size']): # Checks if image is larger than the allowable size, if yes, then generate proxy images to speed up preview generation
                # Downscales the image to a smaller size
                scale_factor = self.class_parameters['max_proxy_size'] / img_size
                x = int(self.RAW_IMG.shape[1] * scale_factor)
                y = int(self.RAW_IMG.shape[0] * scale_factor)
                self.proxy_RAW_IMG = cv2.resize(self.RAW_IMG, (x, y))
                self.proxy = True # Flag to tell the rest of the program that proxies are being used

        # Uses a proxy to generate preview, when needed. During final export, will use full resolution
        if self.proxy and not full_res:
            img = self.proxy_RAW_IMG
        else:
            img = self.RAW_IMG

        dust_mask = self.find_dust(self.crop(img, self.rect))

        # Additional processing specific to each film type
        match self.film_type:
            case 0:
                img = self.bw_negative_processing(img)
            case 1:
                img = self.colour_negative_processing(img)
            case 2:
                img = self.slide_processing(img)
            case 3:
                img = self.crop_only(img)
        
        img = self.crop(img, self.rect)

        self.active_processes -= 1
        if recent_only and (self.active_processes > 0):
            return # skip displaying final image if it is not the last active process

        # Set all the global variables once processing is finished
        self.IMG = img
        self.dust_mask = dust_mask
        self.processed = True

    def bw_negative_processing(self, img):
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) # converts to b/w
        img = 65535 - img # invert to create positive image
        img = self.hist_EQ(img) # increases contrast to maximize dynamic range
        img = self.exposure(img) # exposure adjustment
        img = img.clip(0, 65535).astype(np.uint16, copy=True)
        return img

    def colour_negative_processing(self, img):
        img = 65535 - img # invert to create positive image
        img = self.slide_processing(img) # The rest of the processing is identical to slide_processing
        return img
    
    def slide_processing(self, img):
        img = self.hist_EQ(img) # Maximizes dynamic range
        wb_mode = [self.wb_adjust, self.wb_adjust_coeff, self.wb_adjust_gamma] # different ways to adjust wb, for debugging
        img = wb_mode[1](img) # modifiers for white balancing
        img = self.exposure(img) # Exposure adjustment
        img = self.sat_adjust(img) # modifier for colour saturation
        img = img.clip(0, 65535).astype(np.uint16, copy=True)
        return img
        
    def crop_only(self, img):
        # No processing required
        return img
    
    def find_dust(self, img):
        # work in progress. Tries to detect dust particles of a maximum size, then returns threshold image of just dust
        y, x, _ = img.shape
        img_size = (x + y) / 2
        multiplier = img_size / 800
        max_dust_size = multiplier ** 2 * self.class_parameters['max_dust_area']
        kernel_size = max(round(multiplier) * 2 + 1,1)
        kernel = np.ones((kernel_size,kernel_size),np.uint8)
        x, y = (np.array(self.class_parameters['ignore_border']) / 100 * img.shape[:2][::-1]).astype(np.int32) # calculates the width of the border to ignore in pixels
        if x * y == 0:
            sample = np.s_[:]
        else:
            sample = np.s_[y:-y, x:-x]

        img8 = cv2.convertScaleAbs(img, alpha=(255.0/65535.0))
        imgray = cv2.cvtColor(img8, cv2.COLOR_BGR2GRAY) # converts to b&w
        minimum = np.percentile(imgray[sample], 0.5)
        maximum = np.percentile(imgray[sample], 99.5)
        threshold = (maximum - minimum) * self.class_parameters['dust_threshold'] / 100 + minimum
        _, thresh = cv2.threshold(imgray, threshold, 255, cv2.THRESH_BINARY_INV)
        thresh_img = cv2.dilate(thresh,kernel,iterations = self.class_parameters['dust_iter'])
        thresh_img = cv2.erode(thresh_img,kernel,iterations = self.class_parameters['dust_iter'])
        contours, _ = cv2.findContours(thresh_img, 1, 2)
        contours = sorted(contours, key=lambda x: cv2.contourArea(x))
        smallest = [contour for contour in contours if cv2.contourArea(contour) < max_dust_size]
        dust_mask = np.zeros_like(imgray)
        dust_mask = cv2.drawContours(dust_mask, smallest, -1, 255, cv2.FILLED)
        dust_mask = cv2.dilate(dust_mask, kernel, iterations=1)
        return dust_mask
    
    def fill_dust(self, img, dust_mask):
        # work in progress, uses dust threshold image to erase dust
        if len(img.shape) == 3:
            channels = cv2.split(img)
            filled = []
            for channel in channels:
                filled.append(cv2.inpaint(channel, dust_mask, 3, cv2.INPAINT_TELEA))
            filled = cv2.merge(filled)
        else:
            filled = cv2.inpaint(img, dust_mask, 3, cv2.INPAINT_TELEA)
        return filled

    def find_optimal_crop(self):
        # Determines the optimal crop around an image and corrects for misalignment/rotation
        thresh = self.get_threshold(self.RAW_IMG)
        #thresh = self.get_edges(img) # experimental threholding using edge detection
        contours, _ = cv2.findContours(thresh, 1, 2)
        if len(contours) == 0:
            return thresh, None, None # if no contours are found, skip cropping
        largest_contour = max(contours, key=cv2.contourArea)
        rect = cv2.minAreaRect(largest_contour) # bounding box of largest contour
        y, x = self.RAW_IMG.shape[0], self.RAW_IMG.shape[1]
        rect = ((rect[0][0]/y, rect[0][1]/x), (rect[1][0]/y, rect[1][1]/x), rect[2]) # normalizes crop for different sized images
        return thresh, rect, largest_contour
    
    def crop(self, img, rect, include_EQ_ignore=False):
        if rect is not None:
            if img.shape[0] > img.shape[1]:
                x_crop = self.border_crop
                y_crop = self.border_crop * img.shape[1] / img.shape[0]
            else:
                y_crop = self.border_crop
                x_crop = self.border_crop * img.shape[0] / img.shape[1]
            y, x = img.shape[0], img.shape[1]
            rect = ((rect[0][0]*y, rect[0][1]*x), (rect[1][0]*y, rect[1][1]*x), rect[2]) # convert normalized crop to corresponding pixel coordinates
            box = cv2.boxPoints(rect)
            box = np.int64(box)
            if not (include_EQ_ignore and self.class_parameters['ignore_neg_border']):
                box = self.shrink_box(box, x_crop, y_crop)
            if include_EQ_ignore:
                ignore_border = np.array(self.class_parameters['ignore_border'])
                box = self.shrink_box(box, ignore_border[0], ignore_border[1])
            width = int(rect[1][1] * (1 - x_crop / 100))
            height = int(rect[1][0] * (1 - y_crop / 100))
            src_pts = box.astype('float32')
            dst_pts = np.array([[0, width-1],
                            [0, 0],
                            [height-1, 0],
                            [height-1, width-1]], dtype='float32')
            M = cv2.getPerspectiveTransform(src_pts, dst_pts)
            img = cv2.warpPerspective(img, M, (height, width))
            if rect[2] > 45:
                img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE) # rotates image back if it has been rotated
        return img
    
    def get_edges(self, img):
        # experimental, attempt at smarter image thresholding, not used
        img = cv2.convertScaleAbs(img, alpha=(255.0/65535.0))
        imgray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) # converts to b&w
        blurred = cv2.GaussianBlur(imgray, (5,5), 0)
        max_val = 0
        min_val = abs(self.threshold) / 100 * 255
        edges = cv2.Canny(blurred, min_val, max_val)
        kernel = np.ones((5,5),np.uint8)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 20, None, 50, 10)
        output = np.zeros_like(edges)
        if lines is not None:
            for i in range(0, len(lines)):
                l = lines[i][0]
                cv2.line(output, (l[0], l[1]), (l[2], l[3]), 255, 2, cv2.LINE_AA)
        
        output = cv2.dilate(output,kernel,iterations = 8)
        output = cv2.erode(output,kernel,iterations = 8)
        if self.threshold > 0:
            output = 255 - output
        return output

    def get_threshold(self, img):
        # Generates the threshold image used to find contours
        img = cv2.convertScaleAbs(img, alpha=(255.0/65535.0))
        imgray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) # converts to b&w
        dark_threshold = int(self.dark_threshold / 100 * 255)
        _, dark_thresh_img = cv2.threshold(imgray, dark_threshold, 255, 0)
        light_threshold = int(self.light_threshold / 100 * 255)
        _, light_thresh_img = cv2.threshold(imgray, light_threshold, 255, cv2.THRESH_BINARY_INV)
        thresh_img = cv2.bitwise_and(dark_thresh_img, light_thresh_img)
        kernel = np.ones((7,7),np.uint8)
        thresh_img = cv2.erode(thresh_img, kernel, iterations = 2)
        return thresh_img
    
    def hist_EQ(self, img):
        # Equalizes histogram for each color channel
        sensitivity = 0.2 # multiplier to adjust degree at which the sliders affect the output image

        sample_img = self.crop(img, self.rect, include_EQ_ignore=True)

        if self.base_detect and (self.film_type == 1 or self.film_type == 2):
            if self.film_type == 1:
                black_point = 65535 - np.array(self.base_rgb, np.uint16)[::-1] * 256
            else:
                black_point = np.array(self.base_rgb, np.uint16)[::-1] * 256
        else:
            black_point = np.percentile(sample_img, self.class_parameters['black_point_percentile'], (0,1))
        black_offsets = self.black_point / 100 * sensitivity * 65535 - black_point
        img = img.astype(np.float64, copy=False)
        sample_img = sample_img.astype(np.float32, copy=False)
        
        img[:,:] += black_offsets # Sets the black point
        sample_img[:,:] += black_offsets

        max_array = np.ones_like(black_offsets)
        white_point = np.percentile(sample_img, self.class_parameters['white_point_percentile'], (0,1))
        white_multipliers = np.divide(65535 + self.white_point / 100 * sensitivity * 65535, white_point, out=max_array, where=white_point>0) # division, but ignore divide by zero or negative
        img = np.multiply(img, white_multipliers) # Scales the white percentile to 65535
        return img
    
    # \/ Three different white balance functions experimented with \/
    def wb_adjust(self, img):
        # Applies white balance adjustment factors as scalars added to RGB, not used
        # both highlights' and shadows' white balance affected
        multiplier = 200
        if self.pick_wb: # logic to calculated temp and tint values from the wb picker
            self.pick_wb = False
            x, y, r = self.wb_picker_params # unpacks parameters passed in from white balance picker
            wb_mask = self.rotate(np.zeros_like(self.crop(img, self.rect)[:,:,0], dtype=np.uint8)) # generate blank mask, rotate to same orientation as preview image
            # applying scale factors based on image size
            x = int(x * wb_mask.shape[1])
            y = int(y * wb_mask.shape[0])
            radius = int(min(wb_mask.shape) * r)

            wb_mask = cv2.circle(wb_mask, (x, y), radius, 255, -1) # generate small circle to average pixels with
            wb_mask = self.rotate(wb_mask, True) # rotate image back to default orientation
            meanBGR = cv2.mean(self.crop(img, self.rect), wb_mask) # returns BGR tuple containing average of unmasked pixels
            # calculating temp and tint values required to balance average BGR to gray
            G_offset =  (meanBGR[0] + meanBGR[2]) / 2 - meanBGR[1]
            RB_offset = meanBGR[0] - (meanBGR[0] + meanBGR[2]) / 2
            self.temp = max(min(RB_offset / multiplier, 100), -100)
            self.tint = max(min(G_offset / multiplier, 100), -100)
        adjustment = np.array([-self.temp * multiplier, -self.tint * multiplier, self.temp * multiplier], np.float32)
        img = np.add(img, adjustment)
        return img
    
    def wb_adjust_coeff(self, img):
        # Applies white balance adjustment factors as coefficients multiplied into RGB
        # only highlights white balance affected
        multiplier = 200
        if self.pick_wb: # logic to calculated temp and tint values from the wb picker
            self.pick_wb = False
            x, y, r = self.wb_picker_params # unpacks parameters passed in from white balance picker
            wb_mask = self.rotate(np.zeros_like(self.crop(img, self.rect)[:,:,0], dtype=np.uint8)) # generate blank mask, rotate to same orientation as preview image
            # applying scale factors based on image size
            x = int(x * wb_mask.shape[1])
            y = int(y * wb_mask.shape[0])
            radius = int(min(wb_mask.shape) * r)

            wb_mask = cv2.circle(wb_mask, (x, y), radius, 255, -1) # generate small circle to average pixels with
            wb_mask = self.rotate(wb_mask, True) # rotate image back to default orientation
            B, G, R, _ = cv2.mean(self.crop(img, self.rect), wb_mask) # returns BGR tuple containing average of unmasked pixels
            # calculating temp and tint values required to balance average BGR to gray
            self.tint = max(min((G/B+G/R-2)/((B*(G+R)+R*G)/(B*R)) * multiplier, 100), -100)
            self.temp = max(min(((2*G-(2*G+R)*self.tint/multiplier)/2/R-1) * multiplier, 100), -100)
        
        img = np.multiply(img, np.array([1-self.temp/multiplier+self.tint/multiplier/2, 1-self.tint/multiplier, 1+self.temp/multiplier+self.tint/multiplier/2]))
        return img
    
    def wb_adjust_gamma(self, img):
        # Applies white balance adjustment factors using gamma function, not used
        # Highlights and shadows stay the same, only midtones' white balance affected
        img = img / 65535
        if self.pick_wb: # logic to calculated temp and tint values from the wb picker
            self.pick_wb = False
            x, y, r = self.wb_picker_params # unpacks parameters passed in from white balance picker
            wb_mask = self.rotate(np.zeros_like(self.crop(img, self.rect)[:,:,0], dtype=np.uint8)) # generate blank mask, rotate to same orientation as preview image
            # applying scale factors based on image size
            x = int(x * wb_mask.shape[1])
            y = int(y * wb_mask.shape[0])
            radius = int(min(wb_mask.shape) * r)

            wb_mask = cv2.circle(wb_mask, (x, y), radius, 255, -1) # generate small circle to average pixels with
            wb_mask = self.rotate(wb_mask, True) # rotate image back to default orientation
            meanBGR = cv2.mean(self.crop(img, self.rect), wb_mask) # returns BGR tuple containing average of unmasked pixels
            # calculating temp and tint values required to balance average BGR to gray
            target = (meanBGR[0] + meanBGR[2]) / 2
            self.temp = 100 * np.log2(np.log(target) / np.log(meanBGR[0]))
            self.tint = -100 * np.log2(np.log(target) / np.log(meanBGR[1]))
        
        img = np.power(img, (2 ** np.array([self.temp/100, self.tint/100, -self.temp/100])), dtype=np.float32)

        img = img * 65535 # restores orginal range prior to normalization
        return img
    
    def exposure(self, img):
        # Exposure adjustment
        norm = matplotlib.colors.Normalize(0, 65535, True)
        img = norm(img).astype(np.float32, copy=False)
        
        img = (img ** (2 ** (-self.gamma/100))).astype(np.float32, copy=False) # gamma adjustment via gamma correction
        
        # Highlights and shadows formula
        shadows_coefficient = 4.15e-5 * self.shadows ** 2 + 0.02185 * self.shadows
        img += (shadows_coefficient * np.minimum(img - 0.75, 0) ** 2) * img

        highlights_coefficient = -4.15e-5 * self.highlights ** 2 + 0.02185 * self.highlights
        img += (highlights_coefficient * np.maximum(img - 0.25, 0) ** 2) * (1 - img)

        img = np.ma.getdata(img, False) # converts masked array back to normal array
        
        img = img * 65535 # restores orginal range prior to normalization

        return img
    
    def sat_adjust(self, img):
        # Applies saturation adjustment factors
        if self.sat == 100:
            return img # don't run the calculation if no changes are to be made
        sat_adjust = self.sat / 100
        norm = matplotlib.colors.Normalize(0, 65535, True)
        img = norm(np.flip(img, 2)).astype(np.float32, copy=False) # Convert from bgr to rgb, and normalize input to (0,1)
        img = matplotlib.colors.rgb_to_hsv(img) # Convert from rgb to hsv
        img[:,:,1] = np.clip(img[:,:,1] * sat_adjust, 0, 1) # Apply saturation adjustment
        img = matplotlib.colors.hsv_to_rgb(img) # Convert from hsv back to rgb
        img = np.flip(img, 2) * 65535 # Convert from rgb to bgr
        return img
    
    def rotate(self, img, undo=False):
        # Applies flip and rotation to image
        rotation = self.rotation % 4
        if undo: # option for reverse operation
            if self.flip:
                img = np.ascontiguousarray(img[:,::-1])
            match rotation:
                case 0:
                    pass
                case 1:
                    img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
                case 2:
                    img = cv2.rotate(img, cv2.ROTATE_180)
                case 3:
                    img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        else:
            match rotation:
                case 0: 
                    pass
                case 1: 
                    img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
                case 2: 
                    img = cv2.rotate(img, cv2.ROTATE_180)
                case 3: 
                    img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
            if self.flip:
                img = np.ascontiguousarray(img[:,::-1])
        return img
    
    def draw_histogram(self, img):
        # Generates histogram plot of image
        hist_plot = np.zeros(self.class_parameters['histogram_plt_size'], np.uint8) # Base image for the histogram
        width = self.class_parameters['histogram_plt_size'][1]
        height = self.class_parameters['histogram_plt_size'][0] - 10 # Leave a little border from the top
        histograms = []
        maxes = []
        if len(img.shape) == 2: # Determines if the image is grayscale
            channels = [img]
            colours = [(255, 255, 255)]
        else:
            channels = cv2.split(img)
            colours = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
        bins = [256] # The number of divisions in the histogram
        smoothing = 5
        for channel in channels:
            hist = cv2.calcHist([channel], [0], None, bins, [0, 65536]) # Generates the histogram
            maxes.append(np.max(hist)) # Keeps track of the maximum value of the histogram
            hist[1:-1] = cv2.GaussianBlur(hist[1:-1], (smoothing,smoothing), 0) # Smooths out the histogram
            hist = np.squeeze(hist)
            histograms.append(hist)
        
        for (hist, colour) in zip(histograms, colours):
            if np.max(maxes) != 0:
                hist = hist / np.max(maxes) * height # Scales all histograms to fit in the image
            pts = np.stack((np.linspace(0, width, len(hist)), hist), -1).reshape(-1,1,2).squeeze().tolist() # Reformats hist into a list of 2d points
            pts.insert(0, [0, 0])
            pts.append([width, 0])
            new_plot = np.zeros(self.class_parameters['histogram_plt_size'], np.uint8)
            new_plot = cv2.fillPoly(new_plot, np.array([pts]).astype(np.int32), color=colour) # Generates histogram as a polygon
            hist_plot = hist_plot + new_plot # Add current histogram channel to the overall histogram plot
        return hist_plot
    
    def add_frame(self, img):
        if self.class_parameters['frame'] == 0:
            if self.class_parameters['fit_aspect_ratio'] == 'Keep Original':
                return img # skip if aspect ratio and frame have default values

        frame_size = max(1, int(min(img.shape[:2]) * self.class_parameters['frame'] / 100)) # at least one pixel wide frame
        new_shape = (img.shape[0] + 2 * frame_size, img.shape[1] + 2 * frame_size) + img.shape[2:]
        frame_img = np.ones(new_shape, dtype=img.dtype) * 65535
        frame_img[frame_size:-frame_size, frame_size:-frame_size] = img # center image inside frame

        if self.class_parameters['fit_aspect_ratio'] != 'Keep Original': # fit image to aspect ratio
            target_w, target_h = map(int, self.class_parameters['fit_aspect_ratio'].split(' ', 1)[0].split(':')) # parse 'W:H (text)' to W, H
            target_ratio = target_w / target_h
            current_ratio = frame_img.shape[1] / frame_img.shape[0]
            if current_ratio > target_ratio: # image is wider than target aspect ratio
                new_height = int(frame_img.shape[1] / target_ratio)
                pad = (new_height - frame_img.shape[0]) // 2
                padding = ((pad, pad + (new_height - frame_img.shape[0]) % 2), (0, 0)) + (() if img.ndim == 2 else ((0, 0),))
            else:
                new_width = int(frame_img.shape[0] * target_ratio)
                pad = (new_width - frame_img.shape[1]) // 2
                padding = ((0, 0), (pad, pad + (new_width - frame_img.shape[1]) % 2)) + (() if img.ndim == 2 else ((0, 0),))
            frame_img = np.pad(frame_img, padding, mode='constant', constant_values=65535)

        return frame_img

    def clear_memory(self):
        # Deletes instances of images to save memory
        to_del = ['IMG', 'thresh', 'RAW_IMG', 'proxy_RAW_IMG', 'dust_mask']
        for attr in to_del:
            if hasattr(self, attr):
                delattr(self, attr)
        self.processed = False

    def __sizeof__(self):
        # Returns the size of the largest numpy arrays
        total = 0
        for attr in self.__dict__.keys():
            if type(getattr(self, attr)) is np.ndarray:
                total += getattr(self, attr).nbytes
        return total
    
    def set_wb_from_picker(self, x, y):
        # x, y normalized between 0 and 1 as a proportion along the image height and width
        # r is the radius of a small circle to measure the wb as a proportion of the size of the image
        self.wb_picker_params = (x, y, self.class_parameters['picker_radius'] / 100)
        self.pick_wb = True # sets flag to measure and set white balance on next processing
        self.process()
    
    def get_base_colour(self, x, y):
        # x, y normalized between 0 and 1 as a proportion along the image height and width
        # r is the radius of a small circle to measure the base colour as a proportion of the size of the image
        base_mask = self.rotate(np.zeros_like(self.RAW_IMG[:,:,0], dtype=np.uint8)) # generate blank mask, rotate to same orientation as preview image
        # applying scale factors based on image size
        x = int(x * base_mask.shape[1])
        y = int(y * base_mask.shape[0])
        radius = int(min(base_mask.shape) * self.class_parameters['picker_radius'] / 100)

        base_mask = cv2.circle(base_mask, (x, y), radius, 255, -1) # generate small circle to average pixels with
        base_mask = self.rotate(base_mask, True) # rotate image back to default orientation
        raw = cv2.convertScaleAbs(self.RAW_IMG, alpha=(255.0/65535.0))
        meanBGR = cv2.mean(raw, base_mask)[:-1] # returns BGR tuple containing average of unmasked pixels
        self.base_rgb = tuple([round(x) for x in reversed(meanBGR)])
    
    @staticmethod
    def shrink_box(box, x, y):
        # given box with 4 corner coordinates, returns new box coordinates shrunken by x and y percentages
        sorted = np.sort(box, 0)
        topleft = min(box, key=sum)
        index = np.where(box==topleft)[0][0]
        ordered = np.roll(box, -index, axis=0)
        h = (sorted[2,1] + sorted[3,1] - sorted[0,1] - sorted[1,1]) / 2
        w = (sorted[2,0] + sorted[3,0] - sorted[0,0] - sorted[1,0]) / 2
        skew = (ordered[3,0] - ordered[0,0]) / w * 1.5 # change in y over x-axis
        centre = np.mean(ordered, 0)
        y_offset = y / 100 * h
        x_offset = x / 100 * w
        offset = np.zeros_like(ordered)
        offset[ordered[:,1] < centre[1], 1] += int(y_offset)
        offset[ordered[:,1] > centre[1], 1] -= int(y_offset)
        offset[ordered[:,0] < centre[0], 0] += int(x_offset)
        offset[ordered[:,0] > centre[0], 0] -= int(x_offset)
        for point in offset:
            if point[0] > 0:
                point[1] -= int(x_offset * skew)
            else:
                point[1] += int(x_offset * skew)
            if point[1] < 0:
                point[0] -= int(y_offset * skew)
            else:
                point[0] += int(y_offset * skew)
        new_box = ordered + offset
        new_box = np.roll(new_box, index, axis=0)
        return new_box.astype(np.int32)
