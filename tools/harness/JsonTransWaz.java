import cn.hutool.json.JSONObject;
import cn.hutool.json.JSONUtil;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.giga.nexas.dto.bsdx.waz.Waz;
import com.giga.nexas.dto.bsdx.waz.wazfactory.SkillInfoFactory;
import com.giga.nexas.dto.bsdx.waz.wazfactory.wazinfoclass.SkillUnit;
import com.giga.nexas.dto.bsdx.waz.wazfactory.wazinfoclass.obj.*;
import com.giga.nexas.service.BheBinService;
import com.giga.nexas.service.BsdxBinService;

import java.lang.reflect.Method;
import java.nio.file.*;
import java.util.*;

/**
 * PROTOTYPE: BHE .waz -> BSDX .waz converter that replaces TransMeka's BeanUtil copy with a JSON-level copy
 * (fixes the lost nested BheInfoCollection -> BsdxInfoCollection lists, keeps SkillInfoUnknown lists),
 * then applies NeXAS_DX's existing manual transBheCEventXxxToBsdx() fix-ups for structurally different events.
 * Slot map 83->72 is the one from TransMeka (unmapped BHE slots are dropped and REPORTED).
 *
 * Usage: JsonTransWaz <game/bhe> <outDir> <mech>
 */
public class JsonTransWaz {
    static final int[] MAP = new int[83];
    static {
        for (int i = 0; i <= 22; i++) MAP[i] = i;
        MAP[23] = -1; for (int i = 24; i <= 34; i++) MAP[i] = i - 1;
        MAP[35] = -1; MAP[36] = 34; MAP[37] = 35; MAP[38] = -1; MAP[39] = 36; MAP[40] = -1; MAP[41] = 37; MAP[42] = 38; MAP[43] = -1;
        for (int i = 44; i <= 51; i++) MAP[i] = i - 5;
        MAP[52] = -1; for (int i = 53; i <= 61; i++) MAP[i] = i - 6;
        MAP[62] = -1; for (int i = 63; i <= 65; i++) MAP[i] = i - 7;
        for (int i = 66; i <= 69; i++) MAP[i] = -1;
        for (int i = 70; i <= 82; i++) MAP[i] = i - 11;
    }

    public static void main(String[] a) throws Exception {
        String mech = a[2];
        BheBinService hs = new BheBinService(); BsdxBinService ds = new BsdxBinService();
        var src = (com.giga.nexas.dto.bhe.waz.Waz) hs.parse(a[0] + "/waz/" + mech + ".waz", "windows-31j").getData();
        ObjectMapper om = new ObjectMapper();
        om.configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
        Map<String, Integer> dropped = new TreeMap<>(), manual = new TreeMap<>(), converted = new TreeMap<>();
        Waz dst = new Waz(); dst.setFileName(mech); dst.setExtensionName("waz");
        for (var s : src.getSkillList()) {
            Waz.Skill d = new Waz.Skill();
            if (s.getSkillNameJapanese() == null && (s.getPhasesInfo() == null || s.getPhasesInfo().isEmpty())) { dst.getSkillList().add(d); continue; }
            d.setSkillNameJapanese(s.getSkillNameJapanese()); d.setSkillNameEnglish(s.getSkillNameEnglish());
            for (var sf : s.getSkillSuffixList()) { var t = new Waz.Skill.SkillSuffix(); t.setInt1(sf.getInt1()); t.setInt2(sf.getInt2()); d.getSkillSuffixList().add(t); }
            for (var ph : s.getPhasesInfo()) {
                Waz.Skill.SkillPhase dp = new Waz.Skill.SkillPhase();
                for (var u : ph.getSkillUnitCollection()) {
                    int bs = u.getUnitQuantity(), ts = (bs >= 0 && bs < 83) ? MAP[bs] : -1;
                    if (ts < 0) { dropped.merge("bheSlot" + bs + "(" + u.getUnitDescription() + ")", u.getSkillInfoObjectList().size() + u.getSkillInfoUnknownList().size(), Integer::sum); continue; }
                    SkillUnit du = new SkillUnit(ts, SkillInfoFactory.SKILL_INFO_TYPE_ENTRIES_BSDX[ts].getDescription());
                    for (var ev : u.getSkillInfoObjectList()) {
                        SkillInfoObject proto = SkillInfoFactory.createEventObjectBsdx(ts);
                        SkillInfoObject out;
                        if (bs == 37 && ev instanceof com.giga.nexas.dto.bhe.waz.wazfactory.wazinfoclass.obj.CEventFreeParam fp) {
                            CEventVal v = (CEventVal) proto;   // same rule as TransMeka: take the buffer==0 CEventVal unit
                            v.setStartFrame(fp.getStartFrame()); v.setEndFrame(fp.getEndFrame());
                            v.setInt1(0); v.setInt2(0); v.setInt3(0); v.setInt4(0); // default when no buffer==0 unit (upstream leaves null -> NPE)
                            for (var unit : fp.getUnitList())
                                if (unit.getBuffer() == 0 && unit.getData() instanceof com.giga.nexas.dto.bhe.waz.wazfactory.wazinfoclass.obj.CEventVal sv) {
                                    v.setInt1(sv.getInt1()); v.setInt2(sv.getInt2()); v.setInt3(sv.getInt3()); v.setInt4(sv.getInt4());
                                }
                            out = v; manual.merge("CEventFreeParam->CEventVal", 1, Integer::sum);
                        } else {
                            JSONObject j = JSONUtil.parseObj(JSONUtil.toJsonStr(ev));
                            String js = j.toString().replace("\"bheInfoCollection", "\"bsdxInfoCollection");
                            j = JSONUtil.parseObj(js);
                            remapNested(j, true);
                            j.set("typeId", proto.getTypeId()); j.set("slotNum", ts);
                            out = om.readValue(j.toString(), proto.getClass());
                            // apply existing manual fix-ups (they read BHE-specific getters)
                            String name = proto.getClass().getSimpleName();
                            for (Method m : proto.getClass().getMethods())
                                if (m.getName().equals("transBhe" + name + "ToBsdx")) {
                                    m.invoke(out, ev, out); manual.merge(name, 1, Integer::sum);
                                    if (out.getStartFrame() == null) { out.setStartFrame(ev.getStartFrame()); out.setEndFrame(ev.getEndFrame()); }
                                }
                        }
                        out.setTypeId(proto.getTypeId()); out.setSlotNum(ts);
                        du.getSkillInfoObjectList().add(out);
                        converted.merge(proto.getClass().getSimpleName(), 1, Integer::sum);
                    }
                    for (var un : u.getSkillInfoUnknownList()) {
                        var x = om.readValue(JSONUtil.toJsonStr(un), SkillInfoUnknown.class);
                        du.getSkillInfoUnknownList().add(x);
                    }
                    dp.getSkillUnitCollection().add(du);
                }
                d.getPhasesInfo().add(dp);
            }
            d.setPhaseQuantity(d.getPhasesInfo().size());
            dst.getSkillList().add(d);
        }
        System.out.println("converted events: " + converted);
        System.out.println("manual fix-ups applied: " + manual);
        System.out.println("DROPPED (no BSDX slot): " + dropped);
        Path out = Paths.get(a[1]); Files.createDirectories(out);
        // per-event write->read consistency check
        Map<String, String> bad = new TreeMap<>();
        Path tf = Files.createTempFile("ev", ".waz");
        for (var s : dst.getSkillList()) for (var ph : s.getPhasesInfo()) for (var u : ph.getSkillUnitCollection()) {
            List<Object> items = new ArrayList<>(u.getSkillInfoObjectList()); items.addAll(u.getSkillInfoUnknownList());
            for (Object o : items) {
                String k = o.getClass().getSimpleName() + "@" + u.getUnitQuantity();
                if (bad.containsKey(k)) continue;
                Waz one = new Waz(); one.setExtensionName("waz");
                Waz.Skill sk = new Waz.Skill(); sk.setSkillNameJapanese("x"); sk.setSkillNameEnglish("x"); sk.setPhaseQuantity(1);
                Waz.Skill.SkillPhase p1 = new Waz.Skill.SkillPhase(); SkillUnit uu = new SkillUnit(u.getUnitQuantity(), "");
                if (o instanceof SkillInfoUnknown su) uu.getSkillInfoUnknownList().add(su); else uu.getSkillInfoObjectList().add((SkillInfoObject) o);
                p1.getSkillUnitCollection().add(uu); sk.getPhasesInfo().add(p1); one.getSkillList().add(sk);
                try { ds.generate(tf.toString(), one, "windows-31j"); ds.parse(tf.toString(), "windows-31j"); }
                catch (Throwable e) { Throwable c = e; while (c.getCause() != null) c = c.getCause(); bad.put(k, String.valueOf(c.getMessage())); }
            }
        }
        System.out.println("events failing write->read: " + bad);
        Path f = out.resolve(mech + ".waz");
        ds.generate(f.toString(), dst, "windows-31j");
        var back = (Waz) ds.parse(f.toString(), "windows-31j").getData();
        Path g = out.resolve(mech + ".waz.regen");
        ds.generate(g.toString(), back, "windows-31j");
        System.out.println("generated " + f + " " + Files.size(f) + " B; re-parse OK; skills=" + back.getSkillList().size()
                + "; regen identical=" + Arrays.equals(Files.readAllBytes(f), Files.readAllBytes(g)));
        Files.delete(g);
    }

    /** nested polymorphic SkillInfoObject (e.g. CEventCamera units) carry BHE typeIds -> re-key to a BSDX typeId of the same class */
    static Map<Integer, Integer> TYPE = null;
    static void remapNested(Object node, boolean top) {
        if (TYPE == null) {
            TYPE = new HashMap<>(); Map<String, Integer> bs = new HashMap<>();
            for (int t = 0x23; t >= 0; t--) bs.put(SkillInfoFactory.createCEventObjectByTypeBsdx(t).getClass().getSimpleName(), t);
            for (int t = 0; t <= 0x2B; t++) {
                String n = com.giga.nexas.dto.bhe.waz.wazfactory.SkillInfoFactory.createCEventObjectByTypeBhe(t).getClass().getSimpleName();
                if (bs.containsKey(n)) TYPE.put(t, bs.get(n));
            }
        }
        if (node instanceof JSONObject o) {
            if (!top && o.containsKey("typeId") && o.containsKey("startFrame")) {
                Integer t = o.getInt("typeId");
                if (t != null && TYPE.containsKey(t)) o.set("typeId", TYPE.get(t));
                else if (t != null && t != 255) System.out.println("WARN nested BHE typeId without BSDX class: " + t);
            }
            for (Object v : o.values()) remapNested(v, false);
        } else if (node instanceof cn.hutool.json.JSONArray arr) {
            for (Object v : arr) remapNested(v, false);
        }
    }
}
