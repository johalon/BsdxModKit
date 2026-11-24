import com.giga.nexas.service.BheBinService;
import java.lang.reflect.Method;
import java.nio.file.*;
import java.util.*;
public class DiagPipeline {
  public static void main(String[] a) throws Exception {
    BheBinService hs = new BheBinService();
    Class<?> tm = Class.forName("com.giga.nexas.bhe2bsdx.steps.TransMeka");
    Object src = hs.parse(a[0] + "/waz/tsukuyomi.waz", "windows-31j").getData();
    Method m = tm.getDeclaredMethod("transWaza", com.giga.nexas.dto.bhe.waz.Waz.class); m.setAccessible(true);
    com.giga.nexas.dto.bsdx.waz.Waz w = (com.giga.nexas.dto.bsdx.waz.Waz) m.invoke(null, src);
    Map<String,Integer> nul = new TreeMap<>(), all = new TreeMap<>();
    for (var s : w.getSkillList()) for (var ph : s.getPhasesInfo()) for (var u : ph.getSkillUnitCollection()) for (var o : u.getSkillInfoObjectList()) {
      String k = o.getClass().getSimpleName() + "@slot" + o.getSlotNum();
      all.merge(k, 1, Integer::sum);
      if (o.getStartFrame() == null || o.getEndFrame() == null) nul.merge(k, 1, Integer::sum);
    }
    System.out.println("events with null start/end: " + nul);
    System.out.println("all converted events: " + all);
    Object mk = hs.parse(a[0] + "/mek/tsukuyomi.mek", "windows-31j").getData();
    Method mm = tm.getDeclaredMethod("transMeka", com.giga.nexas.dto.bhe.mek.Mek.class); mm.setAccessible(true);
    com.giga.nexas.dto.bsdx.mek.Mek bm = (com.giga.nexas.dto.bsdx.mek.Mek) mm.invoke(null, mk);
    var wm = bm.getMekWeaponInfoMap();
    System.out.println("mek weapon map value class: " + (wm.isEmpty() ? "empty" : wm.values().iterator().next().getClass()));
    System.out.println("mek AI event class: " + bm.getMekAiInfoList().get(0).getCpuEventList().get(0).getClass());
    System.out.println("mek material entry class: " + ((List<?>) bm.getMekMaterialBlock().getEntries()).get(0).getClass() + " basic=" + bm.getMekBasicInfo().getClass());
  }
}
