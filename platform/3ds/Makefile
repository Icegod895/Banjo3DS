#---------------------------------------------------------------------------------
.SUFFIXES:
#---------------------------------------------------------------------------------

ifeq ($(strip $(DEVKITARM)),)
$(error "Please set DEVKITARM in your environment. export DEVKITARM=<path to>devkitARM")
endif

TOPDIR ?= $(CURDIR)
REPO_ROOT := $(abspath $(TOPDIR)/../..)
BANJO3DS_PYTHON := $(REPO_ROOT)/.venv/bin/python
BANJO3DS_MODEL := $(REPO_ROOT)/assets/model/14CF.model.bin
BANJO3DS_XLU_MODEL := $(REPO_ROOT)/assets/model/14D0.model.bin
BANJO3DS_ACTOR_MODEL := $(REPO_ROOT)/assets/model/034D.model.bin
BANJO3DS_IDLE_ANIMATION := $(REPO_ROOT)/assets/anim/006F.anim.bin
BANJO3DS_WALK_ANIMATION := $(REPO_ROOT)/assets/anim/0003.anim.bin
BANJO3DS_CREEP_ANIMATION := $(REPO_ROOT)/assets/anim/0002.anim.bin
BANJO3DS_RUN_ANIMATION := $(REPO_ROOT)/assets/anim/000C.anim.bin
BANJO3DS_JUMP_ANIMATION := $(REPO_ROOT)/assets/anim/0008.anim.bin
BANJO3DS_CROUCH_ENTER := $(REPO_ROOT)/assets/anim/0001.anim.bin
BANJO3DS_CROUCH_TURN := $(REPO_ROOT)/assets/anim/010C.anim.bin
BANJO3DS_CROUCH_NOINPUT := $(REPO_ROOT)/assets/anim/0116.anim.bin
BANJO3DS_GENERATED_MODEL := $(TOPDIR)/source/generated_model.h
BANJO3DS_GENERATED_CROUCH := $(TOPDIR)/source/generated_crouch.h
BANJO3DS_GENERATED_BRIDGE := $(TOPDIR)/build/generated_bridge.h
BANJO3DS_GENERATED_MOVEMENT_BRIDGE := $(TOPDIR)/build/generated_bridge_movement.h
BANJO3DS_GENERATED_CAMERA := $(TOPDIR)/build/generated_camera.h
BANJO3DS_GENERATED_SFX := $(TOPDIR)/build/generated_sfx_probe.h
BANJO3DS_GENERATED_FOOT := $(TOPDIR)/build/generated_sfx_foot.h
BANJO3DS_ROM ?=
BANJO3DS_BOTTLES_GENERATOR := $(REPO_ROOT)/tools/banjo3ds/bottles_audio/generate.py
BANJO3DS_BOTTLES_HEADERS := $(addprefix $(TOPDIR)/build/,generated_sfx_bottles.h generated_sfx_bottles_remaining.h generated_sfx_bottles_retreat.h)
BANJO3DS_GENERATED_ACTORS := $(TOPDIR)/build/generated_actors.h
BANJO3DS_BOTTLES_MODEL := $(REPO_ROOT)/assets/model/0387.model.bin
BANJO3DS_HILL_MODEL := $(REPO_ROOT)/assets/model/0388.model.bin
BANJO3DS_BOTTLES_IDLE := $(REPO_ROOT)/assets/anim/013B.anim.bin
BANJO3DS_SFX_ROMS := $(wildcard $(REPO_ROOT)/decompressed.us.v10.z64) $(wildcard $(REPO_ROOT)/decompressed.pal.z64)
BANJO3DS_CAMERA_SETUP := $(REPO_ROOT)/assets/lvl_setup/071D.lvl_setup.bin

include $(DEVKITARM)/3ds_rules

#---------------------------------------------------------------------------------
# TARGET is the name of the output
# BUILD is the directory where object files & intermediate files will be placed
# SOURCES is a list of directories containing source code
# DATA is a list of directories containing data files
# INCLUDES is a list of directories containing header files
# GRAPHICS is a list of directories containing graphics files
# GFXBUILD is the directory where converted graphics files will be placed
#   If set to $(BUILD), it will statically link in the converted
#   files as if they were data files.
#
# NO_SMDH: if set to anything, no SMDH file is generated.
# ROMFS is the directory which contains the RomFS, relative to the Makefile (Optional)
# APP_TITLE is the name of the app stored in the SMDH file (Optional)
# APP_DESCRIPTION is the description of the app stored in the SMDH file (Optional)
# APP_AUTHOR is the author of the app stored in the SMDH file (Optional)
# ICON is the filename of the icon (.png), relative to the project folder.
#   If not set, it attempts to use one of the following (in this order):
#     - <Project name>.png
#     - icon.png
#     - <libctru folder>/default_icon.png
#---------------------------------------------------------------------------------
TARGET		:=	banjo3ds
BUILD		:=	build
SOURCES		:=	source ../../tools/banjo3ds/camera_first_person ../../tools/banjo3ds/camera_zones ../../tools/banjo3ds/camera_rail ../../tools/banjo3ds/body ../../tools/banjo3ds/ground ../../tools/banjo3ds/pose ../../tools/banjo3ds/actor_pose ../../tools/banjo3ds/gait ../../tools/banjo3ds/jump ../../tools/banjo3ds/horizontal ../../tools/banjo3ds/camera ../../tools/banjo3ds/camera_contact ../../tools/banjo3ds/world_query ../../tools/banjo3ds/bridge_state ../../tools/banjo3ds/crouch ../../tools/banjo3ds/sfx_probe ../../tools/banjo3ds/footstep
DATA		:=	data
INCLUDES	:=	include source ../../tools/banjo3ds ../../tools/banjo3ds/pose ../../tools/banjo3ds/actor_pose ../../tools/banjo3ds/gait ../../tools/banjo3ds/jump ../../tools/banjo3ds/horizontal ../../tools/banjo3ds/camera ../../tools/banjo3ds/world_query ../../tools/banjo3ds/sfx_probe ../../tools/banjo3ds/footstep
GRAPHICS	:=	gfx
GFXBUILD	:=	$(BUILD)
#ROMFS		:=	romfs
#GFXBUILD	:=	$(ROMFS)/gfx

#---------------------------------------------------------------------------------
# options for code generation
#---------------------------------------------------------------------------------
ARCH	:=	-march=armv6k -mtune=mpcore -mfloat-abi=hard -mtp=soft

CFLAGS	:=	-g -Wall -O2 -mword-relocations \
			-ffunction-sections \
			$(ARCH)

BANJO3DS_DEBUG_CAMERA ?= 0
# Temporary explicit progress input; no save-state integration. Use 0 for tutorial bridge.
BANJO3DS_LEARNED_ABILITIES ?= 0x9DB1
# 1 keeps actor bytes linked and compiles out staged actor behaviour.
BANJO3DS_ACTOR_ISOLATION ?= 1
# 1 uploads actor textures during startup. 0 with vertex init 0 is the FIX2 control.
BANJO3DS_ACTOR_TEXTURE_UPLOAD ?= 1
# 1 allocates the actor vertex buffer and copies the initial vertices once.
# 0 with texture upload 1 and hill draw 0 is the FIX3 control.
BANJO3DS_ACTOR_VERTEX_INIT ?= 1
# 1 draws the original closed molehill. Disable idle and both draws for FIX4.
BANJO3DS_ACTOR_HILL_DRAW ?= 1
# 1 enables the FIX6 Bottles renderer. Disable this and idle for FIX5.
BANJO3DS_ACTOR_STATIC_BOTTLES ?= 1
# 1 enables only the original seven-second idle; 0 reproduces static FIX6.
BANJO3DS_ACTOR_IDLE_ANIMATION ?= 1
# 0 is FIX7; 1 plays original 013D once for 4.5 seconds, then holds CLOSED.
BANJO3DS_ACTOR_HILL_OPEN_ANIMATION ?= 0
# 1 gates B2-P1 once playback on selector-2 proximity; 0 preserves boot playback.
BANJO3DS_ACTOR_HILL_PROXIMITY_TRIGGER ?= 0
# 1 waits for a fresh SELECT press near selector 2; mutually exclusive with auto proximity.
BANJO3DS_ACTOR_HILL_MANUAL_TRIGGER ?= 0
# Opt-in paired emergence hardware diagnostic; 0 retains exact FIX2.
BANJO3DS_ACTOR_BOTTLES_EMERGENCE ?= 0
# Opt-in second SELECT exit; 0 retains hardware-approved B2-P2.
BANJO3DS_ACTOR_BOTTLES_EXIT ?= 0
# Authorized bounded B adapter; default off reproduces B2-P3.
BANJO3DS_ACTOR_BOTTLES_B_INTERACTION ?= 0
# Passive bottom-screen preview; not an original zoombox implementation.
BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PREVIEW ?= 0
# Full DF4 diagnostic; off preserves the approved first-speech preview.
BANJO3DS_ACTOR_BOTTLES_DIALOGUE_SEQUENCE ?= 0
# Completion bridge; off preserves hardware-approved B3-P2-D.
BANJO3DS_ACTOR_BOTTLES_DIALOGUE_AUTO_EXIT ?= 0
# Native dialogue rest adapter; off reproduces hardware-approved B3-P2-E.
BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PLAYER_LOCK ?= 0
ifeq ($(BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PLAYER_LOCK),1)
CFLAGS += -DBANJO3DS_ACTOR_BOTTLES_DIALOGUE_PLAYER_LOCK=1
endif
ifeq ($(BANJO3DS_ACTOR_BOTTLES_DIALOGUE_AUTO_EXIT),1)
CFLAGS += -DBANJO3DS_ACTOR_BOTTLES_DIALOGUE_AUTO_EXIT=1
endif
ifeq ($(BANJO3DS_ACTOR_BOTTLES_DIALOGUE_SEQUENCE),1)
CFLAGS += -DBANJO3DS_ACTOR_BOTTLES_DIALOGUE_SEQUENCE=1
endif
ifeq ($(BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PREVIEW),1)
BANJO3DS_GENERATED_DIALOGUE := $(TOPDIR)/build/generated_dialogue.h
CFLAGS += -DBANJO3DS_ACTOR_BOTTLES_DIALOGUE_PREVIEW=1
endif
ifeq ($(BANJO3DS_ACTOR_BOTTLES_EXIT),1)
BANJO3DS_GENERATED_EXIT := $(TOPDIR)/build/generated_actor_exit.h
endif
ifeq ($(BANJO3DS_ACTOR_BOTTLES_EMERGENCE),1)
BANJO3DS_GENERATED_BOTTLES_EMERGE := $(TOPDIR)/build/generated_bottles_emerge.h
endif
ifeq ($(BANJO3DS_ACTOR_HILL_OPEN_ANIMATION),1)
BANJO3DS_GENERATED_HILL_OPEN := $(TOPDIR)/build/generated_hill_open.h
endif
CFLAGS	+=	$(INCLUDE) -D__3DS__ -DBANJO_DEBUG_CAMERA=$(BANJO3DS_DEBUG_CAMERA) -DBANJO_LEARNED_ABILITIES=$(BANJO3DS_LEARNED_ABILITIES) -DBANJO3DS_ACTOR_ISOLATION=$(BANJO3DS_ACTOR_ISOLATION) -DBANJO3DS_ACTOR_TEXTURE_UPLOAD=$(BANJO3DS_ACTOR_TEXTURE_UPLOAD) -DBANJO3DS_ACTOR_VERTEX_INIT=$(BANJO3DS_ACTOR_VERTEX_INIT) -DBANJO3DS_ACTOR_HILL_DRAW=$(BANJO3DS_ACTOR_HILL_DRAW) -DBANJO3DS_ACTOR_STATIC_BOTTLES=$(BANJO3DS_ACTOR_STATIC_BOTTLES) -DBANJO3DS_ACTOR_IDLE_ANIMATION=$(BANJO3DS_ACTOR_IDLE_ANIMATION) -DBANJO3DS_ACTOR_HILL_OPEN_ANIMATION=$(BANJO3DS_ACTOR_HILL_OPEN_ANIMATION) -DBANJO3DS_ACTOR_HILL_PROXIMITY_TRIGGER=$(BANJO3DS_ACTOR_HILL_PROXIMITY_TRIGGER) -DBANJO3DS_ACTOR_HILL_MANUAL_TRIGGER=$(BANJO3DS_ACTOR_HILL_MANUAL_TRIGGER) -DBANJO3DS_ACTOR_BOTTLES_EMERGENCE=$(BANJO3DS_ACTOR_BOTTLES_EMERGENCE) -DBANJO3DS_ACTOR_BOTTLES_EXIT=$(BANJO3DS_ACTOR_BOTTLES_EXIT) -DBANJO3DS_ACTOR_BOTTLES_B_INTERACTION=$(BANJO3DS_ACTOR_BOTTLES_B_INTERACTION) -Wextra -Werror -ffp-contract=off -fno-fast-math -fexcess-precision=standard

CXXFLAGS	:= $(CFLAGS) -fno-rtti -fno-exceptions -std=gnu++11

ASFLAGS	:=	-g $(ARCH)
LDFLAGS	=	-specs=3dsx.specs -g $(ARCH) -Wl,-Map,$(notdir $*.map)

LIBS	:= -lcitro3d -lctru -lm

#---------------------------------------------------------------------------------
# list of directories containing libraries, this must be the top level containing
# include and lib
#---------------------------------------------------------------------------------
LIBDIRS	:= $(CTRULIB)


#---------------------------------------------------------------------------------
# no real need to edit anything past this point unless you need to add additional
# rules for different file extensions
#---------------------------------------------------------------------------------
ifneq ($(BUILD),$(notdir $(CURDIR)))
#---------------------------------------------------------------------------------

export OUTPUT	:=	$(CURDIR)/$(TARGET)
export TOPDIR	:=	$(CURDIR)

export VPATH	:=	$(foreach dir,$(SOURCES),$(CURDIR)/$(dir)) \
			$(foreach dir,$(GRAPHICS),$(CURDIR)/$(dir)) \
			$(foreach dir,$(DATA),$(CURDIR)/$(dir))

export DEPSDIR	:=	$(CURDIR)/$(BUILD)

CFILES		:=	$(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.c)))
CPPFILES	:=	$(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.cpp)))
SFILES		:=	$(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.s)))
PICAFILES	:=	$(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.v.pica)))
SHLISTFILES	:=	$(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.shlist)))
GFXFILES	:=	$(foreach dir,$(GRAPHICS),$(notdir $(wildcard $(dir)/*.t3s)))
BINFILES	:=	$(foreach dir,$(DATA),$(notdir $(wildcard $(dir)/*.*)))

#---------------------------------------------------------------------------------
# use CXX for linking C++ projects, CC for standard C
#---------------------------------------------------------------------------------
ifeq ($(strip $(CPPFILES)),)
#---------------------------------------------------------------------------------
	export LD	:=	$(CC)
#---------------------------------------------------------------------------------
else
#---------------------------------------------------------------------------------
	export LD	:=	$(CXX)
#---------------------------------------------------------------------------------
endif
#---------------------------------------------------------------------------------

#---------------------------------------------------------------------------------
ifeq ($(GFXBUILD),$(BUILD))
#---------------------------------------------------------------------------------
export T3XFILES :=  $(GFXFILES:.t3s=.t3x)
#---------------------------------------------------------------------------------
else
#---------------------------------------------------------------------------------
export ROMFS_T3XFILES	:=	$(patsubst %.t3s, $(GFXBUILD)/%.t3x, $(GFXFILES))
export T3XHFILES		:=	$(patsubst %.t3s, $(BUILD)/%.h, $(GFXFILES))
#---------------------------------------------------------------------------------
endif
#---------------------------------------------------------------------------------

export OFILES_SOURCES 	:=	$(CPPFILES:.cpp=.o) $(CFILES:.c=.o) $(SFILES:.s=.o)

export OFILES_BIN	:=	$(addsuffix .o,$(BINFILES)) \
			$(PICAFILES:.v.pica=.shbin.o) $(SHLISTFILES:.shlist=.shbin.o) \
			$(addsuffix .o,$(T3XFILES))

export OFILES := $(OFILES_BIN) $(OFILES_SOURCES)

export HFILES	:=	$(PICAFILES:.v.pica=_shbin.h) $(SHLISTFILES:.shlist=_shbin.h) \
			$(addsuffix .h,$(subst .,_,$(BINFILES))) \
			$(GFXFILES:.t3s=.h)

export INCLUDE	:=	$(foreach dir,$(INCLUDES),-I$(CURDIR)/$(dir)) \
			$(foreach dir,$(LIBDIRS),-I$(dir)/include) \
			-I$(CURDIR)/$(BUILD)

export LIBPATHS	:=	$(foreach dir,$(LIBDIRS),-L$(dir)/lib)

export _3DSXDEPS	:=	$(if $(NO_SMDH),,$(OUTPUT).smdh)

ifeq ($(strip $(ICON)),)
	icons := $(wildcard *.png)
	ifneq (,$(findstring $(TARGET).png,$(icons)))
		export APP_ICON := $(TOPDIR)/$(TARGET).png
	else
		ifneq (,$(findstring icon.png,$(icons)))
			export APP_ICON := $(TOPDIR)/icon.png
		endif
	endif
else
	export APP_ICON := $(TOPDIR)/$(ICON)
endif

ifeq ($(strip $(NO_SMDH)),)
	export _3DSXFLAGS += --smdh=$(CURDIR)/$(TARGET).smdh
endif

ifneq ($(ROMFS),)
	export _3DSXFLAGS += --romfs=$(CURDIR)/$(ROMFS)
endif

.PHONY: all clean

ifeq ($(BANJO3DS_ACTOR_ISOLATION),1)
ifeq ($(BANJO3DS_ACTOR_HILL_DRAW),1)
ifeq ($(BANJO3DS_ACTOR_IDLE_ANIMATION),1)
$(info actor-isolation: FIX7 Bottles idle only (IDLE_ANIMATION=1))
else ifeq ($(BANJO3DS_ACTOR_STATIC_BOTTLES),1)
$(info actor-isolation: FIX6 closed molehill and static Bottles (ISOLATION=1 TEXTURE_UPLOAD=1 VERTEX_INIT=1 HILL_DRAW=1 STATIC_BOTTLES=1))
else
$(info actor-isolation: FIX5 closed molehill only (ISOLATION=1 TEXTURE_UPLOAD=1 VERTEX_INIT=1 HILL_DRAW=1))
endif
else
ifeq ($(BANJO3DS_ACTOR_VERTEX_INIT),1)
ifeq ($(BANJO3DS_ACTOR_TEXTURE_UPLOAD),1)
$(info actor-isolation: vertex buffer init (BANJO3DS_ACTOR_ISOLATION=1 BANJO3DS_ACTOR_TEXTURE_UPLOAD=1 BANJO3DS_ACTOR_VERTEX_INIT=1))
else
$(info actor-isolation: vertex buffer init without textures (BANJO3DS_ACTOR_ISOLATION=1 BANJO3DS_ACTOR_TEXTURE_UPLOAD=0 BANJO3DS_ACTOR_VERTEX_INIT=1))
endif
else ifeq ($(BANJO3DS_ACTOR_TEXTURE_UPLOAD),1)
$(info actor-isolation: texture upload only (BANJO3DS_ACTOR_ISOLATION=1 BANJO3DS_ACTOR_TEXTURE_UPLOAD=1))
else
$(info actor-isolation: ALL actor runtime disabled (BANJO3DS_ACTOR_ISOLATION=1 BANJO3DS_ACTOR_TEXTURE_UPLOAD=0))
endif
endif
else
$(info actor-isolation: actor runtime ENABLED (BANJO3DS_ACTOR_ISOLATION=$(BANJO3DS_ACTOR_ISOLATION)))
endif

#---------------------------------------------------------------------------------
all: $(BANJO3DS_GENERATED_DIALOGUE) $(BANJO3DS_GENERATED_EXIT) $(BANJO3DS_GENERATED_BOTTLES_EMERGE) $(BANJO3DS_GENERATED_HILL_OPEN) $(BANJO3DS_GENERATED_MODEL) $(BANJO3DS_GENERATED_CROUCH) $(BANJO3DS_GENERATED_CAMERA) $(BANJO3DS_GENERATED_BRIDGE) $(BANJO3DS_GENERATED_MOVEMENT_BRIDGE) $(BANJO3DS_GENERATED_SFX) $(BANJO3DS_GENERATED_FOOT) $(BANJO3DS_BOTTLES_HEADERS) $(BANJO3DS_GENERATED_ACTORS) $(BUILD) $(GFXBUILD) $(DEPSDIR) $(ROMFS_T3XFILES) $(T3XHFILES)
	@$(MAKE) --no-print-directory -C $(BUILD) -f $(CURDIR)/Makefile
ifeq ($(BANJO3DS_ACTOR_ISOLATION),1)
	@echo actor-isolation: checking $(notdir $(OUTPUT)).elf
	@$(DEVKITARM)/bin/arm-none-eabi-nm $(OUTPUT).elf | grep -q ' actor_isolation_banner$$'
	@! $(DEVKITARM)/bin/arm-none-eabi-nm $(OUTPUT).elf | grep -E ' (sceneDrawPlacedActors|actorDiagStage|actorDiagClear|actor_pose_placement)([.]|$$)'
ifeq ($(BANJO3DS_ACTOR_BOTTLES_EXIT),1)
	@for symbol in bottlesExitPrepare bottlesExitPublish; do $(DEVKITARM)/bin/arm-none-eabi-nm $(OUTPUT).elf | grep -q " $$symbol\$$" || exit 1; done
else
	@! $(DEVKITARM)/bin/arm-none-eabi-nm $(OUTPUT).elf | grep -E ' (bottlesExit|hillClose|actor_bottles_exit_packet|actor_hill_close_packet)'
endif
ifeq ($(BANJO3DS_ACTOR_HILL_OPEN_ANIMATION),1)
	@for symbol in hillOpenPrepare hillOpenPublish; do $(DEVKITARM)/bin/arm-none-eabi-nm $(OUTPUT).elf | grep -q " $$symbol\$$" || exit 1; done
else
	@! $(DEVKITARM)/bin/arm-none-eabi-nm $(OUTPUT).elf | grep -E ' (hillOpen|actor_hill_open_packet)'
endif
ifneq ($(filter 1,$(BANJO3DS_ACTOR_HILL_PROXIMITY_TRIGGER) $(BANJO3DS_ACTOR_HILL_MANUAL_TRIGGER)),)
	@$(DEVKITARM)/bin/arm-none-eabi-nm $(OUTPUT).elf | grep -q ' hillOpenTriggered$$'
else
	@! $(DEVKITARM)/bin/arm-none-eabi-nm $(OUTPUT).elf | grep -E ' (hillOpenTriggered|hillOpenInRange)([.]|$$)'
endif
ifeq ($(BANJO3DS_ACTOR_BOTTLES_EMERGENCE),1)
	@for symbol in bottlesEmergencePrepare bottlesEmergencePublish actor_pose_evaluate_blend; do $(DEVKITARM)/bin/arm-none-eabi-nm $(OUTPUT).elf | grep -q " $$symbol\$$" || exit 1; done
	@! $(DEVKITARM)/bin/arm-none-eabi-nm $(OUTPUT).elf | grep -E ' (bottlesIdlePrepare|bottlesIdlePublish)([.]|$$)'
else
	@! $(DEVKITARM)/bin/arm-none-eabi-nm $(OUTPUT).elf | grep -E ' (bottlesEmergence|actor_pose_evaluate_blend|actor_bottles_emerge_packet)'
ifeq ($(BANJO3DS_ACTOR_IDLE_ANIMATION),1)
	@for symbol in bottlesIdlePrepare bottlesIdlePublish actor_pose_evaluate actor_pose_scatter actor_pose_advance; do $(DEVKITARM)/bin/arm-none-eabi-nm $(OUTPUT).elf | grep -q " $$symbol\$$" || exit 1; done
else
	@! $(DEVKITARM)/bin/arm-none-eabi-nm $(OUTPUT).elf | grep -E ' (bottlesIdlePrepare|bottlesIdlePublish|actor_pose_evaluate|actor_pose_scatter|actor_pose_advance)([.]|$$)'
endif
endif
ifeq ($(BANJO3DS_ACTOR_STATIC_BOTTLES),1)
	@$(DEVKITARM)/bin/arm-none-eabi-nm $(OUTPUT).elf | grep -q ' sceneDrawStaticBottles$$'
else
	@! $(DEVKITARM)/bin/arm-none-eabi-nm $(OUTPUT).elf | grep -E ' sceneDrawStaticBottles([.]|$$)'
endif
ifeq ($(BANJO3DS_ACTOR_HILL_DRAW),1)
	@$(DEVKITARM)/bin/arm-none-eabi-nm $(OUTPUT).elf | grep -q ' sceneDrawClosedMolehill$$'
else
	@! $(DEVKITARM)/bin/arm-none-eabi-nm $(OUTPUT).elf | grep -E ' (sceneDrawClosedMolehill|sceneDrawActorRange)([.]|$$)'
endif
ifeq ($(BANJO3DS_ACTOR_VERTEX_INIT),1)
	@$(DEVKITARM)/bin/arm-none-eabi-nm $(OUTPUT).elf | grep -q ' actor_vbo$$'
	@$(DEVKITARM)/bin/arm-none-eabi-nm $(OUTPUT).elf | grep -q ' initActorVertexBuffer$$'
else
	@! $(DEVKITARM)/bin/arm-none-eabi-nm $(OUTPUT).elf | grep -E ' (actor_vbo|initActorVertexBuffer)$$'
endif
ifeq ($(BANJO3DS_ACTOR_TEXTURE_UPLOAD),1)
	@$(DEVKITARM)/bin/arm-none-eabi-nm $(OUTPUT).elf | grep -q ' uploadActorTextures$$'
else
	@! $(DEVKITARM)/bin/arm-none-eabi-nm $(OUTPUT).elf | grep -E ' uploadActorTextures$$'
endif
ifeq ($(BANJO3DS_ACTOR_IDLE_ANIMATION),1)
	@echo actor-isolation: FIX7 idle updates linked, staged actors absent
else ifeq ($(BANJO3DS_ACTOR_STATIC_BOTTLES),1)
	@echo actor-isolation: FIX6 static Bottles and molehill linked, staged draws and pose symbols absent
else ifeq ($(BANJO3DS_ACTOR_HILL_DRAW),1)
	@echo actor-isolation: FIX5 molehill draw linked, Bottles and pose symbols absent
else ifeq ($(BANJO3DS_ACTOR_VERTEX_INIT),1)
	@echo actor-isolation: vertex buffer init linked, draw and pose symbols absent
else ifeq ($(BANJO3DS_ACTOR_TEXTURE_UPLOAD),1)
	@echo actor-isolation: texture upload linked, draw and pose symbols absent
else
	@echo actor-isolation: runtime symbols absent
endif
endif

$(BANJO3DS_GENERATED_BRIDGE): $(BANJO3DS_XLU_MODEL) $(REPO_ROOT)/tools/banjo3ds/bridge_state/render_binding.py $(REPO_ROOT)/tools/banjo3ds/n64_displaylist_decoder.py | $(BUILD)
	@cd $(REPO_ROOT) && $(BANJO3DS_PYTHON) -B -m tools.banjo3ds.bridge_state.render_binding $(BANJO3DS_XLU_MODEL) $@

$(BANJO3DS_GENERATED_MOVEMENT_BRIDGE): $(BANJO3DS_MODEL) $(BANJO3DS_XLU_MODEL) $(REPO_ROOT)/tools/banjo3ds/bridge_state/movement_binding.py $(REPO_ROOT)/tools/banjo3ds/floor_collision.py | $(BUILD)
	@cd $(REPO_ROOT) && $(BANJO3DS_PYTHON) -B -m tools.banjo3ds.bridge_state.movement_binding $(BANJO3DS_MODEL) $(BANJO3DS_XLU_MODEL) $@ $(TOPDIR)/build/generated_bridge_movement.json

$(BANJO3DS_GENERATED_CAMERA): $(BANJO3DS_MODEL) $(BANJO3DS_XLU_MODEL) $(BANJO3DS_CAMERA_SETUP) $(REPO_ROOT)/tools/banjo3ds/export_camera_data.py $(REPO_ROOT)/tools/banjo3ds/world_query_packet.py $(REPO_ROOT)/tools/banjo3ds/camera/setup.py $(REPO_ROOT)/tools/banjo3ds/camera_zones/setup.py $(REPO_ROOT)/tools/banjo3ds/camera_rail/setup.py | $(BUILD)
	@cd $(REPO_ROOT) && $(BANJO3DS_PYTHON) -B -m tools.banjo3ds.export_camera_data $(BANJO3DS_MODEL) $(BANJO3DS_XLU_MODEL) $(BANJO3DS_CAMERA_SETUP) $@

$(BANJO3DS_GENERATED_MODEL): $(BANJO3DS_MODEL) $(BANJO3DS_XLU_MODEL) $(BANJO3DS_ACTOR_MODEL) $(BANJO3DS_IDLE_ANIMATION) $(REPO_ROOT)/tools/banjo3ds/export_3ds_model.py $(REPO_ROOT)/tools/banjo3ds/n64_displaylist_decoder.py $(REPO_ROOT)/tools/banjo3ds/geo_sort.py $(REPO_ROOT)/tools/banjo3ds/canonical_banjo.py $(REPO_ROOT)/tools/banjo3ds/static_idle.py $(REPO_ROOT)/tools/banjo3ds/floor_collision.py $(REPO_ROOT)/tools/banjo3ds/pose_binding.py $(BANJO3DS_WALK_ANIMATION) $(BANJO3DS_CREEP_ANIMATION) $(BANJO3DS_RUN_ANIMATION) $(BANJO3DS_JUMP_ANIMATION)
	@echo generating $(notdir $@)
	@cd $(REPO_ROOT) && $(BANJO3DS_PYTHON) -B -m tools.banjo3ds.export_3ds_model $(BANJO3DS_MODEL) $(BANJO3DS_GENERATED_MODEL) $(BANJO3DS_XLU_MODEL) $(BANJO3DS_ACTOR_MODEL) $(BANJO3DS_IDLE_ANIMATION) $(BANJO3DS_WALK_ANIMATION) $(BANJO3DS_CREEP_ANIMATION) $(BANJO3DS_RUN_ANIMATION) $(BANJO3DS_JUMP_ANIMATION) --runtime-transitions

$(BANJO3DS_GENERATED_SFX): $(REPO_ROOT)/tools/banjo3ds/sfx_probe_asset.py $(REPO_ROOT)/tools/banjo3ds/sfx_bank.py $(REPO_ROOT)/tools/banjo3ds/sfx_probe/sfx_probe.h $(BANJO3DS_SFX_ROMS) | $(BUILD)
	@echo generating $(notdir $@)
	@cd $(REPO_ROOT) && $(BANJO3DS_PYTHON) -B -m tools.banjo3ds.sfx_probe_asset --out $@ --pcm18 build/sfx/sfx_0018.pcm16 --pcm19 build/sfx/sfx_0019.pcm16

$(BANJO3DS_GENERATED_FOOT): $(REPO_ROOT)/tools/banjo3ds/footstep_asset.py $(REPO_ROOT)/tools/banjo3ds/sfx_bank.py $(REPO_ROOT)/tools/banjo3ds/sfx_probe_asset.py $(BANJO3DS_SFX_ROMS) | $(BUILD)
	@echo generating $(notdir $@)
	@cd $(REPO_ROOT) && $(BANJO3DS_PYTHON) -B -m tools.banjo3ds.footstep_asset --out $@

# Grouped output: removal of any one header regenerates the complete set.
$(BANJO3DS_BOTTLES_HEADERS) &: $(BANJO3DS_BOTTLES_GENERATOR) $(REPO_ROOT)/tools/banjo3ds/sfx_bank.py $(if $(strip $(BANJO3DS_ROM)),$(BANJO3DS_ROM)) | $(BUILD)
	@test -n "$(BANJO3DS_ROM)" || { echo 'Set BANJO3DS_ROM to the verified local US v1.0 cartridge or decompressed ROM' >&2; exit 2; }
	@cd $(REPO_ROOT) && $(BANJO3DS_PYTHON) -B -m tools.banjo3ds.bottles_audio.generate --rom "$(BANJO3DS_ROM)" --output-dir "$(TOPDIR)/build"

ifeq ($(BANJO3DS_ACTOR_HILL_OPEN_ANIMATION),1)
$(BANJO3DS_GENERATED_HILL_OPEN): $(BANJO3DS_HILL_MODEL) $(REPO_ROOT)/assets/anim/013D.anim.bin $(REPO_ROOT)/tools/banjo3ds/actor_mesh.py $(REPO_ROOT)/tools/banjo3ds/n64_displaylist_decoder.py $(REPO_ROOT)/tools/banjo3ds/static_idle.py $(REPO_ROOT)/tools/banjo3ds/canonical_banjo.py | $(BUILD)
	@cd $(REPO_ROOT) && $(BANJO3DS_PYTHON) -B -m tools.banjo3ds.actor_mesh --hill-open-header $@ --hill $(BANJO3DS_HILL_MODEL) --hill-open-animation $(REPO_ROOT)/assets/anim/013D.anim.bin
endif

ifeq ($(BANJO3DS_ACTOR_BOTTLES_EMERGENCE),1)
$(BANJO3DS_GENERATED_BOTTLES_EMERGE): $(BANJO3DS_BOTTLES_MODEL) $(REPO_ROOT)/assets/anim/013A.anim.bin $(REPO_ROOT)/tools/banjo3ds/actor_mesh.py $(REPO_ROOT)/tools/banjo3ds/n64_displaylist_decoder.py $(REPO_ROOT)/tools/banjo3ds/static_idle.py $(REPO_ROOT)/tools/banjo3ds/canonical_banjo.py | $(BUILD)
	@cd $(REPO_ROOT) && $(BANJO3DS_PYTHON) -B -m tools.banjo3ds.actor_mesh --bottles-emerge-header $@ --bottles $(BANJO3DS_BOTTLES_MODEL) --bottles-emerge-animation $(REPO_ROOT)/assets/anim/013A.anim.bin
endif

ifeq ($(BANJO3DS_ACTOR_BOTTLES_EXIT),1)
$(BANJO3DS_GENERATED_EXIT): $(BANJO3DS_BOTTLES_MODEL) $(BANJO3DS_HILL_MODEL) $(REPO_ROOT)/assets/anim/0139.anim.bin $(REPO_ROOT)/assets/anim/013C.anim.bin $(REPO_ROOT)/tools/banjo3ds/actor_mesh.py $(REPO_ROOT)/tools/banjo3ds/n64_displaylist_decoder.py $(REPO_ROOT)/tools/banjo3ds/static_idle.py $(REPO_ROOT)/tools/banjo3ds/canonical_banjo.py | $(BUILD)
	@cd $(REPO_ROOT) && $(BANJO3DS_PYTHON) -B -m tools.banjo3ds.actor_mesh --exit-header $@ --bottles $(BANJO3DS_BOTTLES_MODEL) --hill $(BANJO3DS_HILL_MODEL) --bottles-exit-animation $(REPO_ROOT)/assets/anim/0139.anim.bin --hill-close-animation $(REPO_ROOT)/assets/anim/013C.anim.bin
endif

ifeq ($(BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PREVIEW),1)
$(BANJO3DS_GENERATED_DIALOGUE): $(REPO_ROOT)/assets/dialog/0DF4.dialog $(REPO_ROOT)/assets/dialog/0DF5.dialog $(REPO_ROOT)/assets/dialog/0D38.dialog $(REPO_ROOT)/tools/banjo3ds/dialogue_import.py | $(BUILD)
	@cd $(REPO_ROOT) && $(BANJO3DS_PYTHON) -B -m tools.banjo3ds.dialogue_import --output $@
endif

$(BANJO3DS_GENERATED_ACTORS): $(BANJO3DS_BOTTLES_MODEL) $(BANJO3DS_HILL_MODEL) $(BANJO3DS_BOTTLES_IDLE) $(REPO_ROOT)/tools/banjo3ds/actor_mesh.py $(REPO_ROOT)/tools/banjo3ds/n64_displaylist_decoder.py $(REPO_ROOT)/tools/banjo3ds/export_3ds_model.py $(REPO_ROOT)/tools/banjo3ds/static_idle.py $(REPO_ROOT)/tools/banjo3ds/canonical_banjo.py | $(BUILD)
	@echo generating $(notdir $@)
	@cd $(REPO_ROOT) && $(BANJO3DS_PYTHON) -B -m tools.banjo3ds.actor_mesh --header $@ --bottles $(BANJO3DS_BOTTLES_MODEL) --hill $(BANJO3DS_HILL_MODEL) --idle $(BANJO3DS_BOTTLES_IDLE)

$(BANJO3DS_GENERATED_CROUCH): $(BANJO3DS_CROUCH_ENTER) $(BANJO3DS_CROUCH_TURN) $(BANJO3DS_CROUCH_NOINPUT) $(REPO_ROOT)/tools/banjo3ds/pose_binding.py
	@echo generating $(notdir $@)
	@cd $(REPO_ROOT) && $(BANJO3DS_PYTHON) -B -m tools.banjo3ds.pose_binding --crouch-header $(BANJO3DS_GENERATED_CROUCH) $(BANJO3DS_CROUCH_ENTER) $(BANJO3DS_CROUCH_TURN) $(BANJO3DS_CROUCH_NOINPUT)

$(BUILD):
	@mkdir -p $@

ifneq ($(GFXBUILD),$(BUILD))
$(GFXBUILD):
	@mkdir -p $@
endif

ifneq ($(DEPSDIR),$(BUILD))
$(DEPSDIR):
	@mkdir -p $@
endif

#---------------------------------------------------------------------------------
clean:
	@echo clean ...
	@rm -fr $(BUILD) $(TARGET).3dsx $(OUTPUT).smdh $(TARGET).elf $(GFXBUILD)

#---------------------------------------------------------------------------------
$(GFXBUILD)/%.t3x	$(BUILD)/%.h	:	%.t3s
#---------------------------------------------------------------------------------
	@echo $(notdir $<)
	@tex3ds -i $< -H $(BUILD)/$*.h -d $(DEPSDIR)/$*.d -o $(GFXBUILD)/$*.t3x

#---------------------------------------------------------------------------------
else

#---------------------------------------------------------------------------------
# main targets
#---------------------------------------------------------------------------------
$(OUTPUT).3dsx	:	$(OUTPUT).elf $(_3DSXDEPS)

$(OFILES_SOURCES) : $(HFILES)

$(OUTPUT).elf	:	$(OFILES)

#---------------------------------------------------------------------------------
# you need a rule like this for each extension you use as binary data
#---------------------------------------------------------------------------------
%.bin.o	%_bin.h :	%.bin
#---------------------------------------------------------------------------------
	@echo $(notdir $<)
	@$(bin2o)

#---------------------------------------------------------------------------------
.PRECIOUS	:	%.t3x %.shbin
#---------------------------------------------------------------------------------
%.t3x.o	%_t3x.h :	%.t3x
#---------------------------------------------------------------------------------
	$(SILENTMSG) $(notdir $<)
	$(bin2o)

#---------------------------------------------------------------------------------
%.shbin.o %_shbin.h : %.shbin
#---------------------------------------------------------------------------------
	$(SILENTMSG) $(notdir $<)
	$(bin2o)

-include $(DEPSDIR)/*.d

#---------------------------------------------------------------------------------------
endif
#---------------------------------------------------------------------------------------
