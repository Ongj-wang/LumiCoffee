"""
视觉相机适配器

基于 Orbbec 深度相机实现桌面杂物检测和放置坐标计算。

功能：
1. 拍照获取彩色图 + 深度图
2. 检测桌面目标区域是否有杂物（基于深度差分析）
3. 计算放置坐标（像素→世界坐标转换，利用手眼标定参数）

依赖：
- pyorbbecsdk（Orbbec SDK Python 绑定）
- numpy, cv2
- 手眼标定参数文件（CalibParams.json）
"""

import os
import sys
import json
import logging
import numpy as np
from typing import Optional, Tuple, Dict, Any, List

from controller.devices import DeviceBase, DeviceState
from controller import config

logger = logging.getLogger("controller.devices.vision")


class VisionAdapter(DeviceBase):
    """视觉相机适配器

    封装 Orbbec 深度相机，提供：
    - connect(): 初始化相机（色彩+深度对齐流）
    - capture(): 拍照，获取彩色图和深度数据
    - detect_target(): 综合检测——检查桌面是否有杂物 + 计算放置坐标
    """

    def __init__(self):
        super().__init__("vision")
        self._pipeline = None
        self._camera = None
        self._calib_params: Optional[Dict] = None
        self._last_color_image: Optional[np.ndarray] = None
        self._last_depth_data: Optional[np.ndarray] = None

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------

    def connect(self, host: str = None, port: int = None) -> bool:
        """初始化 Orbbec 深度相机"""
        self._set_state(DeviceState.CONNECTING)

        # 加载手眼标定参数
        self._load_calib_params()

        try:
            # 将 OrbbecSDK 加入 Python 路径
            sdk_dir = config.ORBBEC_SDK_PATH
            if os.path.exists(sdk_dir):
                build_dir = os.path.join(sdk_dir, "pyorbbecsdkMain", "build")
                if os.path.exists(build_dir) and build_dir not in sys.path:
                    sys.path.insert(0, build_dir)
                if sdk_dir not in sys.path:
                    sys.path.insert(0, os.path.dirname(sdk_dir))

            from OrbbecSDK.orbbecCamera import Camera
            self._camera = Camera()
            self._set_state(DeviceState.CONNECTED)
            self._logger.info("Orbbec 深度相机连接成功")
            return True

        except ImportError:
            self._logger.warning("pyorbbecsdk 未安装，视觉模块以 stub 模式运行")
            self._set_state(DeviceState.CONNECTED)
            return True
        except Exception as e:
            self._set_state(DeviceState.ERROR, f"相机连接失败: {e}")
            self._logger.error(f"相机连接失败: {e}")
            return False

    def disconnect(self):
        """关闭相机"""
        if self._camera:
            try:
                self._camera.close()
            except Exception as e:
                self._logger.warning(f"关闭相机异常: {e}")
            self._camera = None
        self._set_state(DeviceState.DISCONNECTED)

    # ------------------------------------------------------------------
    # 拍照
    # ------------------------------------------------------------------

    def get_color_image(self) -> Optional[np.ndarray]:
        """获取一张彩色图像（供标定服务调用）

        Returns:
            BGR 图像数组，失败返回 None
        """
        if not self.is_connected():
            return None

        if self._camera is None:
            # stub 模式：返回空白图
            import cv2
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(img, "Stub Mode - No Camera", (120, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            return img

        try:
            return self._camera.getColorImage()
        except Exception as e:
            self._logger.error(f"获取图像异常: {e}")
            return None

    def has_camera(self) -> bool:
        """是否已连接真实相机"""
        return self._camera is not None

    def capture(self) -> bool:
        """触发拍照，获取彩色图 + 深度数据

        Returns:
            是否成功获取图像
        """
        if not self.is_connected():
            return False

        # stub 模式
        if self._camera is None:
            self._logger.info("触发拍照（stub 模式）")
            self._last_color_image = None
            self._last_depth_data = None
            return True

        try:
            color_image, depth_data, _ = self._camera.getColorDepthData()
            if color_image is None or len(color_image) == 0:
                self._logger.warning("拍照失败：未获取到图像数据")
                return False

            self._last_color_image = color_image
            self._last_depth_data = depth_data
            self._logger.info(f"拍照成功: color={color_image.shape}, depth={'N/A' if depth_data is None else depth_data.shape}")
            return True

        except Exception as e:
            self._logger.error(f"拍照异常: {e}")
            return False

    # ------------------------------------------------------------------
    # 桌面杂物检测
    # ------------------------------------------------------------------

    def check_table_clear(self) -> Tuple[bool, str]:
        """检测桌面目标区域是否有杂物

        原理：在图像中心 ROI 区域内分析深度数据，
        如果深度起伏超过阈值，说明桌面有凸起物（杂物）。

        Returns:
            (is_clear, message)
            - is_clear: True 表示桌面足够干净可以放置
            - message: 检测结果描述
        """
        if self._last_depth_data is None:
            # stub 模式：假设桌面干净
            return True, "stub 模式：假设桌面干净"

        depth = self._last_depth_data
        h, w = depth.shape

        # 计算 ROI 区域（图像中心）
        roi_ratio = config.DETECT_ROI_RATIO
        roi_w = int(w * roi_ratio)
        roi_h = int(h * roi_ratio)
        x_start = (w - roi_w) // 2
        y_start = (h - roi_h) // 2
        roi = depth[y_start:y_start + roi_h, x_start:x_start + roi_w]

        # 过滤无效深度值
        valid_mask = (roi > config.DEPTH_MIN) & (roi < config.DEPTH_MAX)
        valid_depths = roi[valid_mask]

        if len(valid_depths) < 100:
            return False, "深度数据无效或过少，无法判断"

        # 计算桌面基准高度（取中位数，避免离群值影响）
        table_height = np.median(valid_depths)

        # 计算深度偏差（各点到桌面的高度差）
        deviations = np.abs(valid_depths.astype(np.float64) - table_height)

        # 统计超过阈值的点数（凸起物）
        obstacle_threshold = config.TABLE_OBSTACLE_DEPTH_THRESHOLD
        obstacle_points = np.sum(deviations > obstacle_threshold)
        obstacle_ratio = obstacle_points / len(valid_depths)

        # 计算放置所需的最小清晰面积比例
        # 杯底面积 / ROI 面积（近似）
        cup_area_pixels = self._estimate_cup_pixel_area(table_height)
        roi_area = roi_w * roi_h
        min_clear_ratio = cup_area_pixels / roi_area

        self._logger.info(
            f"桌面检测: 基准高度={table_height:.1f}mm, "
            f"杂物比例={obstacle_ratio:.1%}, "
            f"所需清晰比例={min_clear_ratio:.1%}"
        )

        if obstacle_ratio > (1.0 - min_clear_ratio):
            return False, f"桌面杂物过多（{obstacle_ratio:.1%}），无法安全放置"

        return True, f"桌面干净（杂物比例 {obstacle_ratio:.1%}），可以放置"

    def _estimate_cup_pixel_area(self, depth_mm: float) -> float:
        """根据深度距离估算杯底在图像中占的像素面积

        利用相机内参和杯底直径估算：
        pixel_size = real_size * focal_length / depth
        """
        if not self._calib_params:
            return 1000  # 默认估算值

        camera_matrix = self._calib_params.get("CameraMatrix", [])
        if len(camera_matrix) < 3:
            return 1000

        fx = camera_matrix[0][0]
        fy = camera_matrix[1][1]

        # 杯底在图像中的直径（像素）
        cup_diameter_pixels = config.CUP_BASE_DIAMETER * fx / depth_mm

        # 加上安全余量
        total_diameter = cup_diameter_pixels + 2 * (config.PLACEMENT_MARGIN * fx / depth_mm)

        # 圆形面积
        return np.pi * (total_diameter / 2) ** 2

    # ------------------------------------------------------------------
    # 放置坐标计算
    # ------------------------------------------------------------------

    def compute_placement_pose(self) -> Optional[Tuple[float, float, float]]:
        """计算放置坐标

        利用深度数据和手眼标定参数，将图像中心点（桌面放置位置）
        转换为机械臂坐标系下的 (x, y, z)。

        Returns:
            (x, y, z) 机械臂基座坐标系下的放置坐标（mm），失败返回 None
        """
        if self._last_depth_data is None:
            # stub 模式：返回无偏差
            return (0.0, 0.0, 0.0)

        if not self._calib_params:
            self._logger.warning("无标定参数，无法计算放置坐标")
            return (0.0, 0.0, 0.0)

        depth = self._last_depth_data
        h, w = depth.shape

        # 取图像中心点作为放置目标
        center_u = w // 2
        center_v = h // 2

        # 获取中心点深度值（取周围 5x5 区域均值以降噪）
        half = 2
        roi = depth[max(0, center_v - half):center_v + half + 1,
                     max(0, center_u - half):center_u + half + 1]
        valid = roi[(roi > config.DEPTH_MIN) & (roi < config.DEPTH_MAX)]
        if len(valid) == 0:
            self._logger.warning("中心点深度无效")
            return None

        center_depth = float(np.median(valid))

        # 像素坐标 → 世界坐标（机械臂坐标系）
        world_pos = self._pixel_to_world(center_u, center_v, center_depth)
        if world_pos is None:
            return None

        x, y, z = world_pos
        self._logger.info(f"放置坐标计算: pixel=({center_u},{center_v}), depth={center_depth:.1f}mm, world=({x:.1f}, {y:.1f}, {z:.1f})")

        return (x, y, z)

    def _pixel_to_world(self, u: int, v: int, depth: float) -> Optional[Tuple[float, float, float]]:
        """像素坐标转世界坐标

        使用相机内参 + 手眼标定（旋转矩阵 + 平移向量）进行转换。

        Args:
            u, v: 像素坐标
            depth: 该像素的深度值（mm）

        Returns:
            (X, Y, Z) 机械臂基座坐标系下的坐标（mm）
        """
        if not self._calib_params:
            return None

        camera_matrix = self._calib_params.get("CameraMatrix", [])
        R = self._calib_params.get("RotationMat", [])
        T = self._calib_params.get("TranslationMat", [])

        if len(camera_matrix) < 3 or len(R) < 3 or len(T) < 3:
            return None

        # 相机内参
        fx = camera_matrix[0][0]
        fy = camera_matrix[1][1]
        cx = camera_matrix[0][2]
        cy = camera_matrix[1][2]

        # 像素 → 相机坐标系
        x_n = (u - cx) / fx
        y_n = (v - cy) / fy
        P_camera = np.array([depth * x_n, depth * y_n, depth])

        # 相机坐标系 → 机械臂基座坐标系
        R_mat = np.array(R)
        T_vec = np.array(T).reshape(3)
        P_world = np.dot(R_mat, P_camera) + T_vec

        return (float(P_world[0]), float(P_world[1]), float(P_world[2]))

    # ------------------------------------------------------------------
    # 综合检测（状态机调用入口）
    # ------------------------------------------------------------------

    def detect_target(self) -> Optional[Dict[str, Any]]:
        """综合检测：桌面杂物检查 + 放置坐标计算

        Returns:
            检测结果字典：
            {
                "clear": bool,           # 桌面是否干净
                "message": str,          # 检测描述
                "placement_offset": tuple,  # (dx, dy, dz) 放置偏差（mm）
            }
            失败返回 None
        """
        if not self.is_connected():
            return None

        # 1. 桌面杂物检测
        is_clear, message = self.check_table_clear()
        self._logger.info(f"桌面检测: {message}")

        if not is_clear:
            return {
                "clear": False,
                "message": message,
                "placement_offset": None,
            }

        # 2. 计算放置坐标
        offset = self.compute_placement_pose()
        if offset is None:
            return {
                "clear": True,
                "message": "桌面干净但坐标计算失败，使用默认位置",
                "placement_offset": (0.0, 0.0, 0.0),
            }

        return {
            "clear": True,
            "message": message,
            "placement_offset": offset,
        }

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _load_calib_params(self):
        """加载手眼标定参数"""
        calib_path = config.CALIB_PARAMS_PATH
        if os.path.exists(calib_path):
            try:
                with open(calib_path, "r", encoding="utf-8") as f:
                    self._calib_params = json.load(f)
                self._logger.info(f"已加载标定参数: {calib_path}")
            except Exception as e:
                self._logger.warning(f"加载标定参数失败: {e}")
                self._calib_params = None
        else:
            self._logger.warning(f"标定参数文件不存在: {calib_path}")
            self._calib_params = None

    def get_status(self) -> Dict[str, Any]:
        """获取视觉模块状态摘要"""
        base = super().get_status()
        base["has_calib"] = self._calib_params is not None
        base["has_image"] = self._last_color_image is not None
        return base
