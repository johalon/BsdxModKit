import com.giga.nexas.service.*;
import java.lang.reflect.Method;
import java.nio.file.*;
import java.util.*;
public class DiagWaz {
  public static void main(String[] a) throws Exception {
    BheBinService hs = new BheBinService(); BsdxBinService ds = new BsdxBinService();
    Class<?> tm = Class.forName("com.giga.nexas.bhe2bsdx.steps.TransMeka");
    Object src = hs.parse(a[0] + "/waz/tsukuyomi.waz", "windows-31j").getData();
    Method m = tm.getDeclaredMethod("transWaza", com.giga.nexas.dto.bhe.waz.Waz.class); m.setAccessible(true);
    var w = (com.giga.nexas.dto.bsdx.waz.Waz) m.invoke(null, src);
    Path tmp = Files.createTempDirectory("dw");
    // per event class: write single-event skill and re-read
    Map<String,String> res = new TreeMap<>();
    for (var s : w.getSkillList()) for (var ph : s.getPhasesInfo()) for (var u : ph.getSkillUnitCollection()) for (var o : u.getSkillInfoObjectList()) {
      String k = o.getClass().getSimpleName() + "@" + u.getUnitQuantity();
      if (res.containsKey(k) && !res.get(k).equals("ok")) continue;
      var one = new com.giga.nexas.dto.bsdx.waz.Waz(); one.setExtensionName("waz");
      var sk = new com.giga.nexas.dto.bsdx.waz.Waz.Skill(); sk.setSkillNameJapanese("x"); sk.setSkillNameEnglish("x"); sk.setPhaseQuantity(1);
      var p = new com.giga.nexas.dto.bsdx.waz.Waz.Skill.SkillPhase();
      var uu = new com.giga.nexas.dto.bsdx.waz.wazfactory.wazinfoclass.SkillUnit(u.getUnitQuantity(), "");
      uu.getSkillInfoObjectList().add(o); p.getSkillUnitCollection().add(uu); sk.getPhasesInfo().add(p); one.getSkillList().add(sk);
      Path f = tmp.resolve("t.waz");
      try { ds.generate(f.toString(), one, "windows-31j"); ds.parse(f.toString(), "windows-31j"); res.put(k, "ok"); }
      catch (Throwable e) { Throwable c = e; while (c.getCause()!=null) c=c.getCause(); res.put(k, "FAIL " + c.getMessage()); }
    }
    res.forEach((k,v) -> { if (!v.equals("ok")) System.out.println(k + " " + v); });
    System.out.println("classes tested: " + res.size() + ", failing: " + res.values().stream().filter(v->!v.equals("ok")).count());
    long empty = w.getSkillList().stream().filter(s -> s.getSkillNameJapanese()==null).count();
    System.out.println("empty skills: " + empty + " phaseQuantity of empty: " + w.getSkillList().stream().filter(s -> s.getSkillNameJapanese()==null).map(s->String.valueOf(s.getPhaseQuantity())).toList());
  }
}
