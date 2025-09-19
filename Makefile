.PHONY: all clean_dist clean doc debian rpm builddeb buildrpm pre-release release

USERNAME ?= $(shell whoami)
UNAME := $(shell uname)

# 加载 .env
ifneq (,$(wildcard .env))
    include .env
    export
endif

PKG_NAME=mrpt-sensor-imu-taobotics

all:
	@echo "noop for debbuild"
	@echo "可用命令:"
	@echo "  make debian   -> 生成 debian 包模板"
	@echo "  make rpm      -> 生成 rpm 包模板"
	@echo "  make builddeb -> 编译 deb 包"
	@echo "  make buildrpm -> 编译 rpm 包"

doc:
	python setup.py build_sphinx
ifeq ($(UNAME),Darwin)
	@open doc/build/html/index.html
else
	@echo "Not opening index.html on $(UNAME)"
endif

clean_dist:
	-rm -f MANIFEST
	-rm -rf dist deb_dist

clean: clean_dist
	@echo "clean"

debian:
	bloom-generate agirosdebian \
	    --ros-distro $(ROS_DISTRO) \
	    --os-name ubuntu \
	    --os-version jammy

rpm:
	bloom-generate agirosrpm \
	    --ros-distro $(ROS_DISTRO) \
	    --os-name $(OS_NAME) \
	    --os-version $(OS_VERSION)

builddeb:
	cd $(PKG_NAME) && debuild -us -uc

buildrpm:
	rpmbuild -ba $(PKG_NAME)/rpm/agiros-loong-$(PKG_NAME).spec

pre-release:
	NEW_VERSION=$$(python docs/bump_version.py setup.py --version_only) && \
	python docs/bump_version.py setup.py > setup.py_tmp && \
	mv setup.py_tmp setup.py && \
	chmod 775 setup.py && \
	git commit -m "$$NEW_VERSION" setup.py && \
	git tag -f "$$NEW_VERSION"

release: pre-release
	@echo "Now push the result with git push --all"
