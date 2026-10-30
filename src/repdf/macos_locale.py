"""Read display-language preferences independently of Qt's process locale."""
import ctypes


def preferred_languages() -> list[str]:
    from ctypes import c_char_p, c_long, c_void_p

    cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    cf.CFLocaleCopyPreferredLanguages.argtypes = []
    cf.CFLocaleCopyPreferredLanguages.restype = c_void_p
    cf.CFArrayGetCount.argtypes = [c_void_p]
    cf.CFArrayGetCount.restype = c_long
    cf.CFArrayGetValueAtIndex.argtypes = [c_void_p, c_long]
    cf.CFArrayGetValueAtIndex.restype = c_void_p
    cf.CFStringGetLength.argtypes = [c_void_p]
    cf.CFStringGetLength.restype = c_long
    cf.CFStringGetCString.argtypes = [c_void_p, c_char_p, c_long, ctypes.c_uint32]
    cf.CFStringGetCString.restype = ctypes.c_bool
    cf.CFRelease.argtypes = [c_void_p]
    cf.CFRelease.restype = None

    languages = cf.CFLocaleCopyPreferredLanguages()
    if not languages:
        return []
    try:
        result = []
        for index in range(cf.CFArrayGetCount(languages)):
            value = cf.CFArrayGetValueAtIndex(languages, index)
            buffer = ctypes.create_string_buffer(cf.CFStringGetLength(value) * 4 + 1)
            if cf.CFStringGetCString(value, buffer, len(buffer), 0x08000100):  # UTF-8
                language = buffer.value.decode("utf-8")
                if language:
                    result.append(language)
        return result
    finally:
        cf.CFRelease(languages)
