"""
手眼标定服务

封装 LUMI_DEMO-v1 的标定算法，提供 Web 端可调用的标定流程：
1. 采集数据（拍照 + 读取机械臂 TCP 位姿 + 棋盘格角点检测）
2. 运行标定（相机内参 + 手眼标定）
3. 保存结果到 CalibParams.json
"""

import os
import sys
import json
import base64
import logging
import time
from typing import Optional, List, Dict, Any, Tuple

import cv2
import numpy as np

from controller import config

logger = logging.getLogger("controller.calibration")

# 将 LUMI_DEMO-v1 加入 sys.path 以复用标定算法
_LUMI_DEMO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "LUMI_DEMO-v1"
)
if os.path.exists(_LUMI_DEMO_PATH) and _LUMI_DEMO_PATH not in sys.path:
    sys.path.insert(0, _LUMI_DEMO_PATH)


class CalibrationService:
    """手眼标定服务

    依赖：
    - ArmAdapter.get_current_pose() 获取机械臂 TCP 位姿
    - VisionAdapter 的相机拍照能力
    - LUMI_DEMO-v1/utilfs/handToEyeCalibration.py 的标定算法
    """

    def __init__(self, arm_adapter, vision_adapter):
        self._arm = arm_adapter
        self._vision = vision_adapter

        # 采集数据缓存
        self._images: List[np.ndarray] = []
        self._poses: List[List[float]] = []

        # 标定结果
        self._result: Optional[Dict] = None
        self._error_msg: str = ""

    # ------------------------------------------------------------------
    # 数据采集
    # ------------------------------------------------------------------

    def capture_sample(self) -> Dict[str, Any]:
        """采集一组标定数据：拍照 + 读取 TCP 位姿 + 角点检测

        Returns:
            {
                "success": bool,
                "message": str,
                "sample_count": int,
                "preview": str (base64 jpeg),
                "corners_found": bool,
                "pose": [x, y, z, rx, ry, rz],
            }
        """
        # 1. 拍照
        color_image = self._vision.get_color_image()
        if color_image is None:
            return {"success": False, "message": "拍照失败（相机未连接）", "sample_count": len(self._images)}

        # 2. 读取机械臂 TCP 位姿
        pose = self._arm.get_current_pose()
        if pose is None:
            return {
                "success": False,
                "message": "无法获取机械臂位姿，请确认机械臂已连接",
                "sample_count": len(self._images),
            }

        # 3. 棋盘格角点检测
        corners_found = self._detect_corners(color_image)

        # 4. 只有检测到角点才保存
        if corners_found:
            self._images.append(color_image.copy())
            self._poses.append(list(pose))
            msg = f"采集成功（第 {len(self._images)} 组），角点检测通过"
        else:
            msg = f"角点检测失败，本次数据已舍弃（已采集 {len(self._images)} 组）"

        # 5. 生成预览图（base64）
        preview = self._image_to_base64(color_image, corners_found)

        return {
            "success": corners_found,
            "message": msg,
            "sample_count": len(self._images),
            "preview": preview,
            "corners_found": corners_found,
            "pose": list(pose),
        }

    def get_preview(self) -> Optional[str]:
        """获取相机实时预览图（base64）"""
        color_image = self._vision.get_color_image()
        if color_image is None:
            return None


        corners_found = self._detect_corners(color_image)
        return self._image_to_base64(color_image, corners_found)

    # ------------------------------------------------------------------
    # 标定计算
    # ------------------------------------------------------------------

    def run_calibration(self) -> Dict[str, Any]:
        """运行手眼标定

        Returns:
            {
                "success": bool,
                "message": str,
                "result": dict (标定参数) or None,
                "rms": float or None,
            }
        """
        if len(self._images) < config.CALIB_MIN_SAMPLES:
            return {
                "success": False,
                "message": f"采集数据不足，至少需要 {config.CALIB_MIN_SAMPLES} 组，当前 {len(self._images)} 组",
                "result": None,
            }

        try:
            from utilfs.handToEyeCalibration import Calibration

            save_path = config.CALIB_PARAMS_PATH
            os.makedirs(os.path.dirname(save_path), exist_ok=True)

            calibrator = Calibration(
                boardWidth=config.CALIB_BOARD_ROWS,
                boardHeight=config.CALIB_BOARD_COLS,
                squareSize=config.CALIB_SQUARE_SIZE,
                project_name="lumicoffee",
            )

            # 运行标定（process 内部会调用 SaveCalibResult 保存结果）
            calibrator.process(
                self._images,
                np.array(self._poses),
                calib_result_save_path=save_path,
            )

            # 重新加载到 vision_adapter
            self._vision._load_calib_params()

            # 从保存的文件读取结果
            with open(save_path, "r", encoding="utf-8") as f:
                result = json.load(f)

            self._result = result
            logger.info(f"标定完成，结果已保存到 {save_path}")

            return {
                "success": True,
                "message": f"标定完成（{len(self._images)} 组数据），结果已保存",
                "result": result,
            }

        except ImportError:
            return {
                "success": False,
                "message": "标定模块未找到，请确认 LUMI_DEMO-v1 目录存在",
                "result": None,
            }
        except Exception as e:
            logger.error(f"标定失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"标定计算异常: {e}",
                "result": None,
            }

    # ------------------------------------------------------------------
    # 数据管理
    # ------------------------------------------------------------------

    def get_samples(self) -> Dict[str, Any]:
        """获取已采集数据列表"""
        samples = []
        for i, (img, pose) in enumerate(zip(self._images, self._poses)):
            samples.append({
                "index": i,
                "pose": list(pose),
                "preview": self._image_to_base64(img, True),
            })
        return {
            "count": len(samples),
            "min_required": config.CALIB_MIN_SAMPLES,
            "samples": samples,
        }

    def clear_samples(self) -> Dict[str, Any]:
        """清空已采集数据"""
        count = len(self._images)
        self._images.clear()
        self._poses.clear()
        self._result = None
        return {"success": True, "message": f"已清空 {count} 组采集数据", "cleared": count}

    def get_result(self) -> Dict[str, Any]:
        """获取当前标定结果"""
        # 优先返回本次标定结果，否则从文件加载
        if self._result:
            return {"has_result": True, "result": self._result, "source": "calibration"}

        calib_path = config.CALIB_PARAMS_PATH
        if os.path.exists(calib_path):
            try:
                with open(calib_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return {"has_result": True, "result": data, "source": "file"}
            except Exception:
                pass

        return {"has_result": False, "result": None}

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _detect_corners(self, image: np.ndarray) -> bool:
        """检测棋盘格角点"""
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            ret, _ = cv2.findChessboardCorners(
                gray,
                (config.CALIB_BOARD_ROWS, config.CALIB_BOARD_COLS),
                None
            )
            return ret
        except Exception:
            return False

    @staticmethod
    def _image_to_base64(image: np.ndarray, corners_found: bool = False) -> str:
        """将图像转为 base64 JPEG 字符串

        如果 corners_found=True，在图像上绘制角点检测状态标记。
        """
        display = image.copy()

        # 绘制状态标记
        color = (0, 255, 0) if corners_found else (0, 0, 255)
        label = "OK" if corners_found else "NO CORNERS"
        cv2.putText(display, label, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
        cv2.rectangle(display, (0, 0), (display.shape[1] - 1, display.shape[0] - 1), color, 2)

        _, buffer = cv2.imencode('.jpg', display, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return "data:image/jpeg;base64," + base64.b64encode(buffer).decode('utf-8')
