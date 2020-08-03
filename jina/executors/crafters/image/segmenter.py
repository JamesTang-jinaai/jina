from typing import Tuple, Dict, List, Union

import numpy as np

from .. import BaseSegmenter
from .helper import _crop_image, _restore_channel_axis, _load_image, _check_channel_axis


class RandomImageCropper(BaseSegmenter):
    """
    :class:`RandomImageCropper` crops the image with a random crop box. The coordinate is the same coordinate-system
        in the :py:mode:`PIL.Image`.
    """

    def __init__(self,
                 target_size: Union[Tuple[int], int],
                 num_patches: int = 1,
                 channel_axis: int = -1,
                 *args,
                 **kwargs):
        """

        :param target_size: desired output size. If size is a sequence like (h, w), the output size will be matched to
            this. If size is an int, the output will have the same height and width as the `target_size`.
        """
        super().__init__(*args, **kwargs)
        self.target_size = target_size
        self.num_pathes = num_patches
        self.channel_axis = channel_axis

    def craft(self, blob: 'np.ndarray', *args, **kwargs) -> List[Dict]:
        """
        Crop the input image array.

        :param blob: the ndarray of the image
        :return: a list of chunk dicts with the cropped images
        """
        raw_img = _load_image(blob, self.channel_axis)
        result = []
        for i in range(self.num_pathes):
            _img = _crop_image(raw_img, self.target_size, how='random')
            img = _restore_channel_axis(np.asarray(_img), self.channel_axis)
            result.append(
                dict(offset=0, weight=1., blob=np.asarray(img).astype('float32')))
        return result


class FiveImageCropper(BaseSegmenter):
    """
    :class:`FiveImageCropper` crops the image into four corners and the central crop.
    """

    def __init__(self,
                 target_size: int,
                 channel_axis: int = -1,
                 *args,
                 **kwargs):
        """

        :param target_size: desired output size. If size is a sequence like (h, w), the output size will be matched to
            this. If size is an int, the output will have the same height and width as the `target_size`.
        """
        super().__init__(*args, **kwargs)
        self.target_size = target_size
        self.channel_axis = channel_axis

    def craft(self, blob: 'np.ndarray', *args, **kwargs) -> List[Dict]:
        """
        Crop the input image array.

        :param blob: the ndarray of the image with the color channel at the last axis
        :return: a list of five chunk dicts with the cropped images
        """
        raw_img = self.load_image(blob, self.channel_axis)
        image_width, image_height = raw_img.size
        if isinstance(self.target_size, int):
            target_h = target_w = self.target_size
        elif isinstance(self.target_size, Tuple) and len(self.target_size) == 2:
            target_h, target_w = self.target_size
        else:
            raise ValueError(f'target_size should be an integer or a tuple of two integers: {self.target_size}')
        _tl = _crop_image(raw_img, self.target_size, 0, 0)
        tl = _restore_channel_axis(np.asarray(_tl), self.channel_axis)
        _tr = _crop_image(raw_img, self.target_size, image_width - target_w, 0)
        tr = _restore_channel_axis(np.asarray(_tr), self.channel_axis)
        _bl = _crop_image(raw_img, self.target_size, 0, image_height - target_h)
        bl = _restore_channel_axis(np.asarray(_bl), self.channel_axis)
        _br = _crop_image(raw_img, self.target_size, image_width - target_w, image_height - target_h)
        br = _restore_channel_axis(np.asarray(_br), self.channel_axis)
        _center = _crop_image(raw_img, self.target_size, how='center')
        center = _restore_channel_axis(np.asarray(_center), self.channel_axis)
        return [
            dict(offset=0, weight=1., blob=tl.astype('float32')),
            dict(offset=0, weight=1., blob=tr.astype('float32')),
            dict(offset=0, weight=1., blob=bl.astype('float32')),
            dict(offset=0, weight=1., blob=br.astype('float32')),
            dict(offset=0, weight=1., blob=center.astype('float32')),
        ]


class SlidingWindowImageCropper(BaseSegmenter):
    """
    :class:`SlidingWindowImageCropper` crops the image with a sliding window.
    """

    def __init__(self,
                 target_size: int,
                 strides: Tuple[int, int],
                 padding: str = 'VALID',
                 channel_axis: int = -1,
                 *args,
                 **kwargs):
        """

        :param target_size: desired output size. If size is a sequence like (h, w), the output size will be matched to
            this. If size is an int, the output will have the same height and width as the `target_size`.
        :param strides: the strides between two neighboring sliding windows. `strides` is a sequence like (h, w), in
            which denote the strides on the vertical and the horizontal axis.
        :param padding: If `VALID`, only patches which are fully contained in the input image are included. If `SAME`,
            all patches whose starting point is inside the input are included, and areas outside the input default to
            zero. The `padding` argument has no effect on the size of each patch, it determines how many patches are
            extracted. Default is `VALID`.
        """
        super().__init__(*args, **kwargs)
        self.target_size = target_size
        if len(strides) != 2:
            raise ValueError(f'strides should be a tuple of two integers: {strides}')
        self.stride_h, self.stride_w = strides
        self.padding = padding
        self.channel_axis = channel_axis

    def _expand_img(self, img: 'np.ndarray') -> 'np.ndarray':
        h, w, c = img.shape
        ext_h = self.target_size - h % self.stride_h
        ext_w = self.target_size - w % self.stride_w
        return np.pad(img,
                      ((0, ext_h), (0, ext_w), (0, 0)),
                      mode='constant',
                      constant_values=0)

    def craft(self, blob: 'np.ndarray', *args, **kwargs) -> List[Dict]:
        """
        Crop the input image array with a sliding window.

        :param blob: the ndarray of the image with the color channel at the last axis
        :return: a list of chunk dicts with the cropped images.
        """
        raw_img = np.copy(blob)
        raw_img = _check_channel_axis(raw_img, self.channel_axis)
        if self.padding == 'SAME':
            raw_img = self._expand_img(blob)
        h, w, c = raw_img.shape
        row_step = raw_img.strides[0]
        col_step = raw_img.strides[1]
        expanded_img = np.lib.stride_tricks.as_strided(
            raw_img,
            (
                1 + int((h - self.target_size) / self.stride_h),
                1 + int((w - self.target_size) / self.stride_w),
                self.target_size,
                self.target_size,
                c
            ), (
                row_step * self.stride_h,
                col_step * self.stride_w,
                row_step,
                col_step,
                1))
        expanded_img = expanded_img.reshape((-1, self.target_size, self.target_size, c))
        results = []
        for _blob in expanded_img:
            blob = _restore_channel_axis(_blob, self.channel_axis)
            # TODO add location
            results.append(dict(offset=0, weight=1.0, blob=blob.astype('float32')))
        return results
