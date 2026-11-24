import com.giga.nexas.dto.bsdx.dat.Dat;
import com.giga.nexas.dto.bsdx.grp.groupmap.MekaGroupGrp;
import com.giga.nexas.dto.bsdx.grp.groupmap.SpriteGroupGrp;
import com.giga.nexas.dto.bsdx.grp.groupmap.WazaGroupGrp;
import com.giga.nexas.dto.bsdx.mek.Mek;
import com.giga.nexas.dto.bsdx.waz.Waz;
import com.giga.nexas.dto.bsdx.waz.wazfactory.wazinfoclass.SkillUnit;
import com.giga.nexas.dto.bsdx.waz.wazfactory.wazinfoclass.obj.CEventSprite;
import com.giga.nexas.dto.bsdx.waz.wazfactory.wazinfoclass.obj.CEventWazaSelect;
import com.giga.nexas.dto.bsdx.waz.wazfactory.wazinfoclass.obj.SkillInfoObject;
import com.giga.nexas.service.BsdxBinService;

import java.nio.file.*;
import java.util.*;

/**
 * PROTOTYPE (container-only, untested in game): clone an existing BSDX mech into a NEW registry entry.
 *
 * Usage: CloneMech <gameBsdxDir> <outDir> <srcMekName> <newName> [spriteSlot]
 *   e.g. CloneMech .../game/bsdx /path/to/workspace/work/clone_test Sora Test01
 *
 * Writes into <outDir>:
 *   MekaGroup.grp   (+1 entry appended: index = old count)
 *   WazaGroup.grp   (+1 entry appended: index = old count, param = skill count)
 *   SpriteGroup.grp (an EMPTY slot (existFlag=0, default first one, e.g. 133) is filled -> no array-size change,
 *                    so ProgramMaterial.grp and every mek's MaterialBlock keep their 138-wide sprite dimension)
 *   <newName>.mek   (names/indices patched, MaterialBlock sprite list moved from src slot to new slot)
 *   <newName>.waz   (CEventSprite.spmFileSequence src->new, CEventWazaSelect self refs src->new)
 *   <newSpm>.spm    (BYTE COPY of the source spm: SpmGenerator drops trailing data of some files, so never regenerate)
 *   WeaponEquip.dat, BQMekaMemory.dat (+1 row copied from the source mech's row: both have 1 row per MekaGroup entry)
 *   SelectMekaMenu.dat (+1 row: [newMekId, srcRow.col1 (SelectMekaMenuMeka anim), -1])  [semantics partly guessed]
 * Afterwards every written binary is re-parsed and re-generated to check it is self-consistent.
 */
public class CloneMech {
    static final String CS = "windows-31j";
    static BsdxBinService svc = new BsdxBinService();

    @SuppressWarnings("unchecked")
    static <T> T parse(Path p) throws Exception { return (T) svc.parse(p.toString(), CS).getData(); }

    public static void main(String[] a) throws Exception {
        Path game = Paths.get(a[0]), out = Paths.get(a[1]);
        String src = a[2], neu = a[3];
        Files.createDirectories(out);

        MekaGroupGrp mg = parse(game.resolve("grp/MekaGroup.grp"));
        WazaGroupGrp wg = parse(game.resolve("grp/WazaGroup.grp"));
        SpriteGroupGrp sg = parse(game.resolve("grp/SpriteGroup.grp"));
        Mek mek = parse(game.resolve("mek/" + src + ".mek"));

        int srcMekId = -1;
        for (int i = 0; i < mg.getMekaList().size(); i++)
            if (src.equalsIgnoreCase(mg.getMekaList().get(i).getMekaName())) srcMekId = i;
        if (srcMekId < 0) throw new IllegalStateException(src + " not registered in MekaGroup");
        int srcWaz = mek.getMekBasicInfo().getWazFileSequence();
        int srcSpm = mek.getMekBasicInfo().getSpmFileSequence();
        String srcWazFile = wg.getWazaList().get(srcWaz).getWazaDisplayName() + ".waz";
        String srcSpmFile = sg.getSpriteList().get(srcSpm).getSpriteFileName();

        int newSpm = -1;
        if (a.length > 4) newSpm = Integer.parseInt(a[4]);
        else for (int i = 0; i < sg.getSpriteList().size(); i++)
            if (sg.getSpriteList().get(i).getExistFlag() == 0) { newSpm = i; break; }
        if (newSpm < 0 || sg.getSpriteList().get(newSpm).getExistFlag() != 0)
            throw new IllegalStateException("no empty SpriteGroup slot");
        int newMekId = mg.getMekaList().size();
        int newWaz = wg.getWazaList().size();
        String newSpmFile = neu.toLowerCase() + ".spm";
        System.out.printf("src=%s mekId=%d waz=%d(%s) spm=%d(%s)%n", src, srcMekId, srcWaz, srcWazFile, srcSpm, srcSpmFile);
        System.out.printf("new=%s mekId=%d waz=%d spmSlot=%d(%s)%n", neu, newMekId, newWaz, newSpm, newSpmFile);

        // ---- grp registrations
        MekaGroupGrp.MekaGroup me = new MekaGroupGrp.MekaGroup();
        me.setExistFlag(1); me.setMekaName(neu); me.setMekaCodeName(neu.toUpperCase());
        mg.getMekaList().add(me);

        Waz waz = parse(game.resolve("waz/" + srcWazFile));
        WazaGroupGrp.WazaGroupEntry we = new WazaGroupGrp.WazaGroupEntry();
        WazaGroupGrp.WazaGroupEntry wsrc = wg.getWazaList().get(srcWaz);
        we.setExistFlag(1); we.setWazaName(wsrc.getWazaName() + "(複製)"); we.setWazaCodeName(neu.toUpperCase());
        we.setWazaDisplayName(neu); we.setParam(waz.getSkillList().size());
        wg.getWazaList().add(we);

        SpriteGroupGrp.SpriteGroupEntry se = sg.getSpriteList().get(newSpm);
        se.setExistFlag(1); se.setSpriteFileName(newSpmFile); se.setSpriteCodeName(neu.toUpperCase()); se.setParam(0);

        svc.generate(out.resolve("MekaGroup.grp").toString(), mg, CS);
        svc.generate(out.resolve("WazaGroup.grp").toString(), wg, CS);
        svc.generate(out.resolve("SpriteGroup.grp").toString(), sg, CS);

        // ---- mek
        Mek.MekBasicInfo bi = mek.getMekBasicInfo();
        bi.setWazFileSequence(newWaz);
        bi.setSpmFileSequence(newSpm);
        bi.setMekName(bi.getMekName() + "改");
        int moved = 0;
        for (Mek.MekMaterialBlock.PluginEntry e : mek.getMekMaterialBlock().getEntries()) {
            List<int[]> spr = e.getSpriteGroups();
            if (spr.size() <= Math.max(srcSpm, newSpm)) throw new IllegalStateException("material dims " + spr.size());
            if (spr.get(newSpm).length != 0) throw new IllegalStateException("target sprite slot not empty in material");
            if (spr.get(srcSpm).length != 0) { spr.set(newSpm, spr.get(srcSpm)); spr.set(srcSpm, new int[0]); moved++; }
        }
        System.out.println("material entries remapped: " + moved + "/" + mek.getMekMaterialBlock().getEntries().size());
        svc.generate(out.resolve(neu + ".mek").toString(), mek, CS);

        // ---- waz
        int[] cnt = new int[2];
        for (Waz.Skill s : waz.getSkillList())
            for (Waz.Skill.SkillPhase ph : s.getPhasesInfo())
                for (SkillUnit u : ph.getSkillUnitCollection())
                    for (SkillInfoObject o : u.getSkillInfoObjectList()) {
                        if (o instanceof CEventSprite && ((CEventSprite) o).getSpmFileSequence() == srcSpm) {
                            ((CEventSprite) o).setSpmFileSequence(newSpm); cnt[0]++;
                        }
                        if (o instanceof CEventWazaSelect && ((CEventWazaSelect) o).getWazFileNo() == srcWaz) {
                            ((CEventWazaSelect) o).setWazFileNo(newWaz); cnt[1]++;
                        }
                    }
        System.out.println("waz remap: CEventSprite=" + cnt[0] + " CEventWazaSelect(self)=" + cnt[1]);
        svc.generate(out.resolve(neu + ".waz").toString(), waz, CS);

        // ---- spm: byte copy
        Files.copy(game.resolve("spm/" + srcSpmFile), out.resolve(newSpmFile), StandardCopyOption.REPLACE_EXISTING);

        // ---- dat tables with one row per MekaGroup entry
        for (String dn : List.of("WeaponEquip", "BQMekaMemory")) {
            Dat d = parse(game.resolve("dat/" + dn + ".dat"));
            if (d.getData().size() != newMekId) System.out.println("WARN " + dn + " rows=" + d.getData().size() + " != MekaGroup " + newMekId);
            d.getData().add(new ArrayList<>(d.getData().get(srcMekId)));
            svc.generate(out.resolve(dn + ".dat").toString(), d, CS);
        }
        Dat sel = parse(game.resolve("dat/SelectMekaMenu.dat"));
        List<Object> srow = null;
        for (List<Object> r : sel.getData()) if (((Number) r.get(0)).intValue() == srcMekId) srow = r;
        if (srow != null) {
            List<Object> nr = new ArrayList<>(srow); nr.set(0, newMekId); nr.set(2, -1);
            sel.getData().add(nr);
            svc.generate(out.resolve("SelectMekaMenu.dat").toString(), sel, CS);
        } else System.out.println("source mech not in SelectMekaMenu.dat; skipped");

        // ---- self-check: every output re-parses and re-generates byte-identically
        Path chk = Files.createTempDirectory("clonechk");
        try (DirectoryStream<Path> ds = Files.newDirectoryStream(out)) {
            for (Path p : ds) {
                if (p.toString().endsWith(".spm")) continue;
                Object o = svc.parse(p.toString(), CS).getData();
                Path g = chk.resolve(p.getFileName());
                svc.generate(g.toString(), (com.giga.nexas.dto.bsdx.Bsdx) o, CS);
                System.out.println((Arrays.equals(Files.readAllBytes(p), Files.readAllBytes(g)) ? "selfcheck OK  " : "selfcheck BAD ") + p.getFileName());
            }
        }
    }
}
