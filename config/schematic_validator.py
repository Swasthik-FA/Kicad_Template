#!/usr/bin/env python3
# ============================================================================
# Phase 2 schematic validator
# ----------------------------------------------------------------------------
# Generic, no-config power-pin and decoupling-cap checker. Reads a KiCad XML
# netlist (kicad-cli sch export netlist --format kicadxml) and flags:
#
#   * power-input pins floating (not on any net)
#   * power pins on non-power signal nets
#   * power pins shorted to GND
#   * GND-named pins on non-GND nets / floating
#   * voltage-named pins on a mismatched rail (e.g. pin "3V3" on +5V net)
#   * IC power pins with no decoupling capacitor between rail and GND
#
# Detection is purely heuristic from pin names + electrical types + net names:
# no per-project config required. Rule classifications:
#   error   -> hard connectivity violations (floating, shorted, wrong polarity)
#   warning -> probable issues that need a human eye (mismatched rail, missing
#              decoupling) — these are heuristic and may have false positives
# ============================================================================
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

POWER_PIN_NAMES = {
    'VCC', 'VDD', 'VDDA', 'VDDD', 'AVDD', 'DVDD', 'AVCC', 'DVCC',
    'V+', 'VS', 'VIN', 'VBAT', 'VBUS', 'VSYS', 'VPP', 'VREF',
    '3V3', '+3V3', '3.3V', '+3.3V',
    '5V', '+5V', 'VCC5',
    '1V8', '+1V8', '1.8V',
    '2V5', '+2V5', '2.5V',
    '12V', '+12V',
}

GND_PIN_NAMES = {
    'GND', 'VSS', 'VSSA', 'VSSD',
    'AGND', 'DGND', 'GNDA', 'GNDD', 'PGND', 'EGND', '0V',
}

GND_NET_PATTERNS = [
    re.compile(r'^/?(A|D|P|E)?GND([_/].*)?$', re.IGNORECASE),
    re.compile(r'^/?VSS[AD]?$', re.IGNORECASE),
    re.compile(r'^/?0V$', re.IGNORECASE),
]

POWER_NET_PATTERNS = [
    re.compile(r'^/?\+?\d+V\d*$', re.IGNORECASE),
    re.compile(r'^/?\+?\d+\.\d+V?$', re.IGNORECASE),
    re.compile(r'^/?V(CC|DD|IN|BAT|BUS|SYS|PP|REF)', re.IGNORECASE),
    re.compile(r'^/?\+?(AV|DV)(CC|DD)', re.IGNORECASE),
]


def normalize(name):
    return (name or '').strip().upper().replace(' ', '')


def is_gnd_net(name):
    return any(p.match(name or '') for p in GND_NET_PATTERNS)


def is_power_net(name):
    if not name or is_gnd_net(name):
        return False
    return any(p.match(name) for p in POWER_NET_PATTERNS)


def is_power_pin(pin_name, pin_type):
    if (pin_type or '').lower() == 'power_in':
        return True
    return normalize(pin_name) in POWER_PIN_NAMES


def is_gnd_pin(pin_name):
    return normalize(pin_name) in GND_PIN_NAMES


def voltage_token(s):
    """Canonicalize a voltage in a pin or net name -> e.g. '3V3', '5V', or None."""
    if not s:
        return None
    m = re.search(r'(\d+)[V\.](\d+)', s, re.IGNORECASE)
    if m:
        minor = m.group(2).rstrip('V')
        return f"{m.group(1)}V{minor}" if minor else f"{m.group(1)}V"
    m = re.search(r'(\d+)V', s, re.IGNORECASE)
    if m:
        return f"{m.group(1)}V"
    return None


def is_capacitor(ref):
    return bool(ref) and ref[0] == 'C' and ref[1:2].isdigit()


def parse_netlist(path):
    root = ET.parse(path).getroot()

    components = {}
    for c in root.findall('./components/comp'):
        ref = c.get('ref')
        ls = c.find('libsource')
        libsource = (ls.get('lib'), ls.get('part')) if ls is not None else (None, None)
        components[ref] = {
            'value': (c.findtext('value') or '').strip(),
            'libsource': libsource,
        }

    libparts = {}
    for lp in root.findall('./libparts/libpart'):
        key = (lp.get('lib'), lp.get('part'))
        pins = {}
        for p in lp.findall('./pins/pin'):
            pins[p.get('num')] = (p.get('name', ''), p.get('type', ''))
        libparts[key] = pins

    nets = defaultdict(list)
    for n in root.findall('./nets/net'):
        name = n.get('name', '')
        for node in n.findall('./node'):
            nets[name].append((node.get('ref'), node.get('pin')))

    return components, nets, libparts


def validate(netlist_path):
    components, nets, libparts = parse_netlist(netlist_path)

    # ref -> {pin_num: net_name}
    comp_pin_net = defaultdict(dict)
    for net_name, nodes in nets.items():
        for ref, pin in nodes:
            comp_pin_net[ref][pin] = net_name

    # Map: rail-net -> [cap refs that bridge it to GND]
    cap_supports = defaultdict(list)
    for ref, comp in components.items():
        if not is_capacitor(ref):
            continue
        pin_to_net = comp_pin_net.get(ref, {})
        if len(pin_to_net) < 2:
            continue
        nets_on_cap = set(pin_to_net.values())
        if any(is_gnd_net(n) for n in nets_on_cap):
            for n in nets_on_cap:
                if not is_gnd_net(n):
                    cap_supports[n].append(ref)

    errors, warnings = [], []

    def add(bucket, rule, ref, pin, pin_name, detail):
        bucket.append({
            'rule': rule, 'ref': ref, 'pin': pin,
            'pin_name': pin_name, 'detail': detail,
        })

    for ref, comp in components.items():
        pins_def = libparts.get(comp['libsource'], {})
        for pin_num, (pin_name, pin_type) in pins_def.items():
            net = comp_pin_net.get(ref, {}).get(pin_num)

            if is_gnd_pin(pin_name):
                if not net:
                    add(errors, 'gnd_pin_floating', ref, pin_num, pin_name,
                        'GND pin not connected to any net')
                elif not is_gnd_net(net):
                    add(errors, 'gnd_pin_wrong_net', ref, pin_num, pin_name,
                        f'GND-named pin connected to non-GND net "{net}"')
                continue

            if not is_power_pin(pin_name, pin_type):
                continue

            if not net:
                add(errors, 'power_pin_floating', ref, pin_num, pin_name,
                    'Power pin not connected to any net')
                continue
            if is_gnd_net(net):
                add(errors, 'power_pin_shorted_to_gnd', ref, pin_num, pin_name,
                    f'Power pin connected to GND net "{net}"')
                continue
            if not is_power_net(net):
                add(errors, 'power_pin_on_signal_net', ref, pin_num, pin_name,
                    f'Power pin connected to non-power net "{net}"')
                continue

            pin_v, net_v = voltage_token(pin_name), voltage_token(net)
            if pin_v and net_v and pin_v != net_v:
                add(warnings, 'voltage_name_mismatch', ref, pin_num, pin_name,
                    f'Pin "{pin_name}" (~{pin_v}) on rail "{net}" (~{net_v})')

            if is_capacitor(ref):
                continue
            if not cap_supports.get(net):
                add(warnings, 'missing_decoupling_cap', ref, pin_num, pin_name,
                    f'No decoupling capacitor found between "{net}" and GND')

    return errors, warnings


def render_html(errors, warnings, out_path):
    def row(sev, v):
        return (f'<tr class="{sev}"><td>{sev}</td><td>{v["rule"]}</td>'
                f'<td>{v["ref"]}</td><td>{v["pin"]}</td>'
                f'<td>{v["pin_name"]}</td><td>{v["detail"]}</td></tr>')
    body = ''.join(row('error', v) for v in errors) + \
           ''.join(row('warning', v) for v in warnings)
    if not body:
        body = '<tr><td colspan="6">No issues found.</td></tr>'
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Schematic validator report</title>
<style>
body{{font-family:system-ui,sans-serif;margin:2rem;color:#222;}}
h1{{margin-bottom:.2rem;}}
table{{border-collapse:collapse;width:100%;margin-top:1rem;}}
th,td{{border:1px solid #ccc;padding:.4rem .6rem;text-align:left;font-size:.9rem;}}
th{{background:#f6f6f6;}}
tr.error td:first-child{{color:#b00;font-weight:bold;}}
tr.warning td:first-child{{color:#a60;font-weight:bold;}}
</style></head><body>
<h1>Schematic validator</h1>
<p>{len(errors)} error(s), {len(warnings)} warning(s).</p>
<table><thead><tr><th>Severity</th><th>Rule</th><th>Ref</th><th>Pin</th>
<th>Pin name</th><th>Detail</th></tr></thead>
<tbody>{body}</tbody></table>
</body></html>"""
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--netlist', required=True)
    ap.add_argument('--report-html', required=True)
    ap.add_argument('--report-json', required=True)
    args = ap.parse_args()

    errors, warnings = validate(args.netlist)
    render_html(errors, warnings, args.report_html)
    with open(args.report_json, 'w', encoding='utf-8') as f:
        json.dump({'errors': errors, 'warnings': warnings}, f, indent=2)

    print(f"Schematic validator: {len(errors)} error(s), {len(warnings)} warning(s).")
    for v in errors:
        print(f"  ERROR  [{v['rule']}] {v['ref']} pin {v['pin']} ({v['pin_name']}): {v['detail']}")
    for v in warnings:
        print(f"  WARN   [{v['rule']}] {v['ref']} pin {v['pin']} ({v['pin_name']}): {v['detail']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
