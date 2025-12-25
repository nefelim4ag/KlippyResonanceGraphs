#!/usr/bin/env python3

import os
import time
import subprocess

from threading import Thread
from queue import Queue
from KlippyRPCShim import KlippyRPCShim

class Error(Exception):
    pass

info = {
    "method": "info",
    "params": {
        "client_info": {
            "program": "ResonanceGraphs", "version": "0.0.1"
        }
    }
}

def main():
    krpc = KlippyRPCShim()

    # Register itself and test connection
    while True:
        resp = krpc.query({"method": "info"})
        result = resp["result"]
        if result["state"] == "ready":
            break
        time.sleep(2)
    krpc.query(info)

    q_objects = {"method": "objects/list"}
    resp = krpc.query(q_objects)
    objects = resp["result"]["objects"]

    # Query for response and resonance_tester
    if "configfile" not in objects:
        raise Error("Well, we are not ready to live without config")

    # Not intuitive, api status reference can help to choose the correct section to query
    describe_object = { "method": "objects/query", "params": {"objects": {"configfile": ["settings"]}}}
    settings = krpc.query(describe_object)["result"]["status"]["configfile"]["settings"]
    if "resonance_tester" not in settings:
        raise Error("Nothing to do without resonance tester")

    resonance_tester = settings["resonance_tester"]

    sensor_name_x = sensor_name_y = resonance_tester.get("accel_chip")
    if sensor_name_x is None:
        sensor_name_x = resonance_tester.get("accel_chip_x")
    if sensor_name_y is None:
        sensor_name_y = resonance_tester.get("accel_chip_y")

    def gcmd_run(cmd):
        q = { "method": "gcode/script", "params": {"script": f"{cmd}"}}
        resp = krpc.query(q)
        if "error" in resp:
            msg = resp["error"]["message"]
            raise Error(msg)

    # Define some way to communicate back
    if "respond" not in settings:
        raise Error("No way to give user feedback")

    def kprint(msg, error=False):
        t = "command"
        if error:
            t = "error"
        gcmd_run(f"RESPOND TYPE={t} MSG='{msg}'")

    probe_points = resonance_tester["probe_points"]
    params_q = Queue(1)
    krpc.register_remote_method(callback=params_q.put, remote_method="test_resonances")
    while True:
        resp = params_q.get()
        axis = resp["axis"]
        x, y, z = probe_points[0]
        try:
            gcmd_run(f"SAVE_GCODE_STATE NAME=manual_resonance_run")
            gcmd_run(f"G90")
            gcmd_run(f"G0 X{x} Y{y} Z{z}")
            gcmd_run(f"M400")

            # Subscribe to accelerometer data
            request = {"method": "adxl345/dump_adxl345", "params": {"sensor": f"{sensor_name_x}"}}
            file_name = f"/home/{os.environ["USER"]}/printer_data/config/raw_dump_{axis}_{time.strftime("%Y%m%d_%H%M%S")}.csv"
            generator, cancel = krpc.subscribe(request)
            f = open(file_name, "w")
            f.write("#time,accel_x,accel_y,accel_z\n")
            def _bg_writer():
                for resp in generator():
                    params = resp.get("params")
                    if params is None:
                        continue
                    d = params["data"]
                    for t, accel_x, accel_y, accel_z in d:
                        f.write("%.6f,%.6f,%.6f,%.6f\n" % (t, accel_x, accel_y, accel_z))
            wth = Thread(target=_bg_writer)
            wth.start()
            gcmd_run(f"TEST_RESONANCES AXIS={axis}")
            cancel()
            wth.join()

            cmd = [f"/home/{os.environ["USER"]}/klipper/scripts/calibrate_shaper.py"]
            cmd += [f"{file_name}"]
            cmd += ["-o"] + [f"/home/{os.environ["USER"]}/printer_data/config/shaper_{axis}_graph.png"]
            # Generate graphs
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )
            kprint(result.stdout)
        except Error as e:
            kprint(e, error=True)
        gcmd_run(f"RESTORE_GCODE_STATE NAME=manual_resonance_run MOVE=1")
    # print(settings)


    # Test subscription
    # import statistics
    # request = {"method": "adxl345/dump_adxl345", "params": {"sensor": "adxl345"}}
    # pkgs = 5
    # generator, cancel = krpc.subscribe(request)
    # for resp in generator():
    #     params = resp.get("params")
    #     if params is None:
    #         continue
    #     d = params["data"]
    #     val = [row[1] for row in d]

    #     # Compute mean and standard deviation
    #     mean_val = statistics.mean(val)
    #     stddev_val = statistics.stdev(val) if len(val) > 1 else 0.0

    #     print(f"Mean value: {mean_val:.3f}, StdDev: {stddev_val:.3f}")
    #     pkgs -= 1
    #     if pkgs <= 0:
    #         cancel()

if __name__ == "__main__":
    main()
