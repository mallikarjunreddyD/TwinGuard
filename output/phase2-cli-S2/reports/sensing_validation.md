# Virtual sensor-model validation

Computed comparisons against separately stored modeled references. These are not physical sensor accuracy or anomaly detection results.

```json
{
  "validation_kind": "restricted virtual sensor model verification; no physical calibration or anomaly detection",
  "scenario_id": "S2",
  "fidelity": "L1",
  "lidar": {
    "S2-lidar-01-t_0": {
      "emitted_rays": 11520,
      "valid_returns": 5511,
      "valid_return_fraction": 0.4783854166666667,
      "visible_ray_fraction": 0.4875,
      "range_error_m": {
        "count": 5511,
        "rmse": 0.004132724178461234,
        "mean": 3.2844227232072954e-05,
        "std": 0.00413259366402936,
        "mae": 0.003281356805498063
      },
      "translation_error_m": 0.019555897421150582,
      "rotation_error_rad": 0.0034437473992140082,
      "actual_outlier_returns": 0
    },
    "S2-lidar-01-t_60": {
      "emitted_rays": 11520,
      "valid_returns": 5214,
      "valid_return_fraction": 0.45260416666666664,
      "visible_ray_fraction": 0.4597222222222222,
      "range_error_m": {
        "count": 5214,
        "rmse": 0.0041061585874830045,
        "mean": -4.487371354605255e-05,
        "std": 0.004105913381379715,
        "mae": 0.0032749376170571713
      },
      "translation_error_m": 0.024454501409569642,
      "rotation_error_rad": 0.0032646244028314447,
      "actual_outlier_returns": 0
    }
  },
  "thermal": {
    "S2-thermal-01-t_60": {
      "total_pixels": 12288,
      "valid_pixels": 7191,
      "valid_fraction": 0.585205078125,
      "apparent_model_error_c": {
        "count": 7191,
        "rmse": 0.2992858637552489,
        "mean": -0.0005932125485741562,
        "std": 0.2992852758533196,
        "mae": 0.2382341463233648
      },
      "surface_temperature_difference_c": {
        "count": 7191,
        "rmse": 4.366853907519071,
        "mean": -4.0642276611944625,
        "std": 1.5973310763884743,
        "mae": 4.09460041172235
      }
    }
  },
  "iot": {
    "drum-thermometer": {
      "expected": 13,
      "received_messages": 13,
      "unique_observations": 13,
      "completeness": 1.0,
      "measurement_error": {
        "count": 13,
        "rmse": 0.23276976257233797,
        "mean": -0.09577437786435675,
        "std": 0.21215331935342893,
        "mae": 0.1753806697229637
      },
      "delayed_messages": 10,
      "duplicates": 0,
      "out_of_order": 0
    },
    "load-01": {
      "expected": 61,
      "received_messages": 59,
      "unique_observations": 59,
      "completeness": 0.9672131147540983,
      "measurement_error": {
        "count": 59,
        "rmse": 0.0017969288418245917,
        "mean": -6.134790555593129e-05,
        "std": 0.0017958813148604696,
        "mae": 0.0014177880509568892
      },
      "delayed_messages": 47,
      "duplicates": 0,
      "out_of_order": 0
    },
    "pipe-temperature": {
      "expected": 25,
      "received_messages": 25,
      "unique_observations": 25,
      "completeness": 1.0,
      "measurement_error": {
        "count": 25,
        "rmse": 0.21276701399233466,
        "mean": -0.014000716833481874,
        "std": 0.21230586937567927,
        "mae": 0.16428158460290207
      },
      "delayed_messages": 18,
      "duplicates": 0,
      "out_of_order": 0
    },
    "pressure-01": {
      "expected": 121,
      "received_messages": 119,
      "unique_observations": 119,
      "completeness": 0.9834710743801653,
      "measurement_error": {
        "count": 119,
        "rmse": 145.3154455527692,
        "mean": -16.091813820830993,
        "std": 144.42171666392676,
        "mae": 113.08905860295073
      },
      "delayed_messages": 104,
      "duplicates": 0,
      "out_of_order": 0
    },
    "pressure-02": {
      "expected": 41,
      "received_messages": 41,
      "unique_observations": 41,
      "completeness": 1.0,
      "measurement_error": {
        "count": 41,
        "rmse": 154.5488400681877,
        "mean": 26.45887111346862,
        "std": 152.2671077607476,
        "mae": 134.87045402932492
      },
      "delayed_messages": 33,
      "duplicates": 0,
      "out_of_order": 0
    },
    "temperature-01": {
      "expected": 61,
      "received_messages": 62,
      "unique_observations": 61,
      "completeness": 1.0,
      "measurement_error": {
        "count": 61,
        "rmse": 0.2098784680228014,
        "mean": 0.02667147992260149,
        "std": 0.20817685629852406,
        "mae": 0.1681028090558383
      },
      "delayed_messages": 48,
      "duplicates": 1,
      "out_of_order": 0
    },
    "vibration-01": {
      "expected": 61,
      "received_messages": 62,
      "unique_observations": 60,
      "completeness": 0.9836065573770492,
      "measurement_error": {
        "count": 60,
        "rmse": 0.004687831745423268,
        "mean": -0.0008101189454969246,
        "std": 0.004617301567749839,
        "mae": 0.0036394989442073257
      },
      "delayed_messages": 51,
      "duplicates": 2,
      "out_of_order": 0
    },
    "vibration-02": {
      "expected": 25,
      "received_messages": 26,
      "unique_observations": 25,
      "completeness": 1.0,
      "measurement_error": {
        "count": 25,
        "rmse": 0.0045932933668574125,
        "mean": 0.002307379231709452,
        "std": 0.0039716929683816455,
        "mae": 0.003859852437014097
      },
      "delayed_messages": 17,
      "duplicates": 1,
      "out_of_order": 0
    },
    "wall-thermometer": {
      "expected": 25,
      "received_messages": 26,
      "unique_observations": 25,
      "completeness": 1.0,
      "measurement_error": {
        "count": 25,
        "rmse": 0.23475618727723613,
        "mean": -0.0013205577342171183,
        "std": 0.23475247302683602,
        "mae": 0.1830715220312902
      },
      "delayed_messages": 21,
      "duplicates": 1,
      "out_of_order": 0
    }
  },
  "acquisition_runtime_s": {
    "S2-lidar-01-t_0": 1.0813098030048423,
    "S2-lidar-01-t_60": 0.02032476500608027,
    "S2-thermal-01-t_60": 0.020100494992220774,
    "iot": 1.02472064900212
  },
  "resource_measurement": {
    "process_peak_rss_mib": 684.171875,
    "scope": "Linux process peak RSS including interpreter/backend/plant/acquisition"
  }
}
```
