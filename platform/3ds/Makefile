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
SOURCES		:=	source ../../tools/banjo3ds/camera_first_person ../../tools/banjo3ds/camera_zones ../../tools/banjo3ds/camera_rail ../../tools/banjo3ds/body ../../tools/banjo3ds/ground ../../tools/banjo3ds/pose ../../tools/banjo3ds/gait ../../tools/banjo3ds/jump ../../tools/banjo3ds/horizontal ../../tools/banjo3ds/camera ../../tools/banjo3ds/camera_contact ../../tools/banjo3ds/world_query ../../tools/banjo3ds/bridge_state ../../tools/banjo3ds/crouch ../../tools/banjo3ds/sfx_probe ../../tools/banjo3ds/footstep
DATA		:=	data
INCLUDES	:=	include source ../../tools/banjo3ds ../../tools/banjo3ds/pose ../../tools/banjo3ds/gait ../../tools/banjo3ds/jump ../../tools/banjo3ds/horizontal ../../tools/banjo3ds/camera ../../tools/banjo3ds/world_query ../../tools/banjo3ds/sfx_probe ../../tools/banjo3ds/footstep
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
CFLAGS	+=	$(INCLUDE) -D__3DS__ -DBANJO_DEBUG_CAMERA=$(BANJO3DS_DEBUG_CAMERA) -DBANJO_LEARNED_ABILITIES=$(BANJO3DS_LEARNED_ABILITIES) -Wextra -Werror -ffp-contract=off -fno-fast-math -fexcess-precision=standard

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

#---------------------------------------------------------------------------------
all: $(BANJO3DS_GENERATED_MODEL) $(BANJO3DS_GENERATED_CROUCH) $(BANJO3DS_GENERATED_CAMERA) $(BANJO3DS_GENERATED_BRIDGE) $(BANJO3DS_GENERATED_MOVEMENT_BRIDGE) $(BANJO3DS_GENERATED_SFX) $(BANJO3DS_GENERATED_FOOT) $(BUILD) $(GFXBUILD) $(DEPSDIR) $(ROMFS_T3XFILES) $(T3XHFILES)
	@$(MAKE) --no-print-directory -C $(BUILD) -f $(CURDIR)/Makefile

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
